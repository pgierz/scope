# -*- coding: utf-8 -*-

"""Main module."""

import subprocess
import os

import click


def determine_cdo_openMP():
    cmd = "cdo --version"
    cdo_ver = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    cdo_ver = cdo_ver.decode("utf-8")
    for line in cdo_ver.split("\n"):
        if line.startswith("Features"):
            return "OpenMP" in line
    return False


class SimObj(object):

    NAME = "Generic Sim Object"

    def after_run(self):
        print(
            "This hook could be run after a supercompter job is finished for ",
            self.NAME,
        )

    def before_recieve(self):
        print("This hook could be run recieving information into the generic layer!")

    def before_send(self):
        print(
            "This hook could be run before sending information into the generic layer!"
        )

    def send(self):
        raise NotImplementedError("You haven't overriden the send method, sorry!")

    def recieve(self):
        raise NotImplementedError("You haven't overriden the recieve method, sorry!")


class Model(SimObj):

    NAME = "Generic Model Object"

    def __init__(self):
        print("Model set up!")


class Component(SimObj):

    NAME = "Generic Component Object"

    def __init__(self):
        print("Component set up!")


class Scope(object):
    def __init__(self, config, whos_turn):
        self.config = config
        self.whos_turn = whos_turn

    def get_cdo_prefix(self, has_openMP=determine_cdo_openMP()):
        if has_openMP:
            return "cdo -P " + str(self.config["number openMP processes"])
        else:
            return "cdo"


class Preprocess(Scope):
    def all_senders(self):
        if self.config[self.whos_turn].get("send"):
            for sender in self.config[self.whos_turn].get("send"):
                yield {sender: self.config[self.whos_turn]["send"][sender]}

    def _construct_filelist(self, var_dict):
        r = re.compile(var_dict["files"]["pattern"])
        all_files = os.listdir(
            var_dict["files"].get(
                "directory", self.config[self.whos_turn].get("outdata_directory")
            )
        )
        # Just the matching files:
        # TODO: Fix the sorted, its probably wrong...
        matching_files = sorted(
            [f for f in all_files if r.match(f)], key=lambda x: os.path.getmtime(x)
        )
        if "take" in var_dict["files"]:
            if "newest" in var_dict["files"]["take"]:
                take = var_dict["files"]["take"]["newest"]
                return matching_files[:take]
            elif "oldest" in var_dict["files"]["take"]:
                take = var_dict["files"]["take"]["oldest"]
                return reversed(matching_files[:take])
            elif "specific" in var_dict["files"]["take"]:
                return var_dict["files"]["take"]["specific"]
        else:
            return matching_files


class Regrid(Scope):
    def _calculate_weights(self, Model, Type, Interp):
        regrid_weight_file = os.path.join(
            self.config["scope"]["couple_dir"],
            "_".join([self.config[Model]["type"], Type, Interp, "weight_file.nc"]),
        )

        cdo_command = (
            self.get_cdo_prefix()
            + " gen"
            + Interp
            + ","
            + self.config[Model]["griddes"]
            + " "
            + Type
            + "_file_for_"
            + self.config[Model]["type"]
            + ".nc"
            + " "
            + regrid_weight_file
        )

        if not os.path.isfile(regrid_weight_file):
            click.secho("Calculating weights: ", fg="cyan")
            click.secho(cdo_command, fg="cyan")
            subprocess.run(cdo_command, shell=True, check=True)
        return regrid_weight_file

    def regrid(self):
        if self.config[self.whos_turn].get("recieve"):
            for sender_type in self.config[self.whos_turn].get("recieve"):
                if self.config[self.whos_turn]["recieve"].get(sender_type):
                    for Variable in self.config[self.whos_turn]["recieve"].get(
                        sender_type
                    ):
                        Model = self.whos_turn
                        Type = sender_type
                        Interp = (
                            self.config[self.whos_turn]
                            .get("recieve")
                            .get(sender_type)
                            .get(Variable)
                            .get("interp")
                        )
                        self.regrid_one_var(Model, Type, Interp, Variable)

    def regrid_one_var(self, Model, Type, Interp, Variable):
        weight_file = self._calculate_weights(Model, Type, Interp)
        cdo_command = (
            self.get_cdo_prefix()
            + " remap,"
            + self.config[Model]["griddes"]
            + ","
            + weight_file
            + " "
            + "-selvar,"
            + Variable
            + " "
            + Type
            + "_file_for_"
            + self.config[Model]["type"]
            + ".nc "
            + Type
            + "_"
            + Variable
            + "_for_"
            + self.config[Model]["type"]
            + "_on_"
            + self.config[Model]["type"]
            + "_grid.nc"
        )
        click.secho("Remapping: ", fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)
