# -*- coding: utf-8 -*-

"""Main module."""

import logging
import os
import re
import subprocess

import click


def determine_cdo_openMP():
    """
    Checks if the ``cdo`` version being used supports ``OpenMP``; useful to
    check if you need a ``-P`` flag or not.
    """
    cmd = "cdo --version"
    cdo_ver = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    cdo_ver = cdo_ver.decode("utf-8")
    for line in cdo_ver.split("\n"):
        if line.startswith("Features"):
            return "OpenMP" in line
    return False


class Scope(object):
    def __init__(self, config, whos_turn):
        self.config = config
        self.whos_turn = whos_turn

        if not os.path.isdir(config["scope"]["couple_dir"]):
            os.makedirs(config["scope"]["couple_dir"])

    def get_cdo_prefix(self, has_openMP=None):
        if not has_openMP:
            has_openMP = determine_cdo_openMP()
        if has_openMP:
            return "cdo -P " + str(self.config["scope"]["number openMP processes"])
        else:
            return "cdo"


class Preprocess(Scope):
    def preprocess(self):
        for (sender_type, sender_args) in self._all_senders():
            for variable_name, variable_dict in sender_args.items():
                logging.debug("The following files will be used for:", variable_name)
                self._make_tmp_files_for_variable(variable_name, variable_dict)
            self._combine_tmp_variable_files(sender_type)

    def _all_senders(self):
        if self.config[self.whos_turn].get("send"):
            for reciever_type in self.config[self.whos_turn].get("send"):
                yield (
                    reciever_type,
                    self.config[self.whos_turn]["send"][reciever_type],
                )

    def _construct_filelist(self, var_dict):
        """

        Example
        -------
        The variable configuration dictionary can have the following top-level **keys**:
        * ``files`` may contain:
            * a ``filepattern`` in regex to look for
            * ``take`` which files to take, either specific, or
              ``newest``/``latest`` followed by an integer.
            * ``dir`` a directory where to look for the files. Note that if
              this is not provided, the default is to fall back to the top level
              ``outdata_dir`` for the currently sending model.
        """
        r = re.compile(var_dict["files"]["pattern"])
        file_directory = var_dict["files"].get(
            "dir", self.config[self.whos_turn].get("outdata_dir")
        )

        all_files = []
        for rootname, _, filenames in os.walk(file_directory):
            for filename in filenames:
                full_name = os.path.join(rootname, filename)
                all_files.append(full_name)
            break  # Do not go into subdirectories

        # Just the matching files:
        matching_files = sorted([f for f in all_files if r.match(os.path.basename(f))])
        if "take" in var_dict["files"]:
            if "newest" in var_dict["files"]["take"]:
                take = var_dict["files"]["take"]["newest"]
                return matching_files[-take:]
            elif "oldest" in var_dict["files"]["take"]:
                take = var_dict["files"]["take"]["oldest"]
                return matching_files[:take]
            # FIXME: This is wrong:
            elif "specific" in var_dict["files"]["take"]:
                return var_dict["files"]["take"]["specific"]
        else:
            return matching_files

    def _make_tmp_files_for_variable(self, varname, var_dict):
        """
        Generates temporary files for further processing with ``scope``.

        Given a variable name and a description dictionary of how it should be
        extracted and processed, this method makes a temporary file,
        ``<sender_name>_<varname>_file_for_scope.nc``, e.g.
        ``echam_temp2_file_for_scope.nc`` in the ``couple_dir``.

        Parameters
        ----------
        varname : str
            Variable name as that should be selected from the files
        var_dict : dict
            A configuration dictionary describing how the variable should be
            extracted. An example is given in ``_construct_filelist``.

        Notes
        -----
        In addition to the dictionary description of ``files``, further
        information may be added with the following top-level keys:

        * ``code table`` describing which ``GRIB`` code numbers correspond to
          which variables. If not given, the fallback value is the value of
          ``code table`` in the sender configuration.

        Returns
        -------
        None

        Notes
        -----
        Converts any input file to ``nc`` via `cdo`. Runs both ``select`` and ``settable``.
        """
        flist = self._construct_filelist(var_dict)
        for f in flist:
            print("- ", f)
        code_table = var_dict.get(
            "code table", self.config[self.whos_turn].get("code table")
        )
        cdo_command = (
            self.get_cdo_prefix()
            + " -f nc -t "
            + code_table
            + " -select,name="
            + varname
            + " "
            + " ".join(flist)
            + " "
            + self.config["scope"]["couple_dir"]
            + "/"
            + self.whos_turn
            + "_"
            + varname
            + "_file_for_scope.nc"
        )

        click.secho(
            "Selecting %s for further processing with SCOPE..." % varname, fg="cyan"
        )
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)

    # TODO/FIXME: This function does not work correctly if there are different
    # time axis for each variable. It might be better to just leave each
    # variable in it's own file.
    def _combine_tmp_variable_files(self, reciever_type):
        """
        Combines all files in the couple directory for a particular reciever type.

        Depending on the configuration, this method combines all files found in
        the ``couple_dir`` which may have been further processed by ``scope``
        to a file ``<sender_type>_file_for_<reciever_type>.nc``

        Parameters
        ----------
        reciever_type : str
            Which reciever the model is sending to, e.g. ice, ocean, atmosphere

        Returns
        -------
        None

        Note
        ----
        This executes a ``cdo mergetime`` command to concatenate all files found which
        should be sent to particular model.
        """
        print(reciever_type)
        reciever = (
            self.config.get(self.whos_turn, {}).get("send", {}).get(reciever_type, {})
        )
        variables_to_send_to_reciever = list(reciever)
        files_to_combine = []
        for f in os.listdir(self.config["scope"]["couple_dir"]):
            fvar = f.replace(self.whos_turn+"_", "").replace("_file_for_scope.nc", "")
            if fvar in variables_to_send_to_reciever:
                files_to_combine.append(os.path.join(self.config["scope"]["couple_dir"], f))
        output_file = os.path.join(
                self.config["scope"]["couple_dir"],
                self.config[self.whos_turn]['type'] + "_file_for_" + reciever_type+".nc"
                )
        cdo_command = (
                self.get_cdo_prefix()
                + " mergetime "
                + " ".join(files_to_combine)
                + " "
                + output_file
                )
        click.secho("Combine files for sending to %s" % reciever_type, fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)



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
            + self.config["scope"]["couple_dir"]
            + "/"
            + self.config[Model]["griddes"]
            + " "
            + self.config["scope"]["couple_dir"]
            + "/"
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
