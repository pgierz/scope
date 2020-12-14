#!/usr/bin/env python3
"""
Here, the ``scope`` library is described. This allows you to use specific parts
of ``scope`` from other programs.

``scope`` consists of several main classes. Note that most of them provide
Python access to ``cdo`` calls via Python's built-in ``subprocess`` module.
Without a correctly installed ``cdo``, many of these functions/classes will not
work.


We provide a quick summary, but please look at the documentation for each
function and class for more complete information. The following functions are
defined:

* ``determine_cdo_openMP`` -- using ``cdo --version``, determines if you have
  openMP support.

The following classes are defined here:

* ``Scope`` -- an abstract base class useful for starting other classes from.
  This provides a way to determine if ``cdo`` has openMP support or not by
  parsing ``cdo --version``. Additionally, it has a nested class which gives
  you decorators to put around methods for enabling arbitrary shell calls
  before and after the method is executed, which can be configured via the
  ``Scope.config`` dictionary.

* ``Send`` -- a class to extract and combine various NetCDF files for
  further processing.

* ``Recieve`` -- a class to easily regrid from one model to another, depending
  on the specifications in the ``scope_config.yaml``

- - - - - -
"""

from functools import wraps
import os
import pathlib
import re
import subprocess
import sys
import warnings

import click
from loguru import logger

# logging.basicConfig(level=logging.DEBUG)


def determine_cdo_openMP() -> bool:
    """
    Checks if the ``cdo`` version being used supports ``OpenMP``; useful to
    check if you need a ``-P`` flag or not.

    Parameters
    ----------
    None

    Returns
    -------
    bool :
        True if ``OpenMP`` is listed in the Features of ``cdo``, otherwise
        False
    """
    cmd = "cdo --version"
    cdo_ver = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    cdo_ver = cdo_ver.decode("utf-8")
    for line in cdo_ver.split("\n"):
        if line.startswith("Features"):
            return "OpenMP" in line
    return False


def determine_fileextension(f: str) -> str:
    result = (
        subprocess.check_output(f"cdo -s --no_warnings showformat {f}", shell=True)
        .decode("utf-8")
        .strip()
    )
    return result


def suggest_fileext(f: str) -> str:
    """
    Given a file, uses CDO to determine which file extension is should have,
    and gives back an appropriate string that can be used for renaming.
    """
    result = determine_fileextension(f)
    current_extension = pathlib.Path(f).suffix
    suggested_f = f.replace(current_extension, "." + result.lower())
    logger.debug(f"{f} is actually a {result} file")
    logger.debug(f"It could be renamed {suggested_f}")
    return suggested_f


def rename_with_suggested_fileext(f: str) -> None:
    """Renames a file with the suggested file extension"""
    new_f = suggest_fileext(f)
    os.rename(f, new_f)
    return new_f


def get_newest_n_timesteps(f: str, take: int) -> str:
    """
    Given a file, takes the newest n timesteps for further processing.

    Parameters
    ----------
    f : str
        The file to use.
    take : int
        Number of timesteps to take (newest will be taken, i.e. from the end of
        the file). Please use a positive value!

    Returns
    -------
    str :
        A string with the path to the new file
    """
    if not take > 0:
        raise ValueError("Please supply a positive integer as the ``take`` argument!")
    cdo_command = (
        "cdo "
        + " -f nc "
        + " -seltimestep,"
        + str(-take)
        + "/-1 "
        + f
        + " "
        + f.replace(".nc", "_newest_" + str(take) + "_timesteps.nc")
    )
    click.secho(
        "Selecting newest %s timesteps for further processing " % str(take), fg="cyan"
    )
    click.secho(cdo_command, fg="cyan")
    subprocess.run(cdo_command, shell=True, check=True)
    return f.replace(".nc", "_newest_" + str(int) + "_timesteps.nc")


def get_oldest_n_timesteps(f: str, take: int) -> str:
    """
    Given a file, takes the oldest n timesteps for further processing.

    Parameters
    ----------
    f : str
        The file to use.
    take : int
        Number of timesteps to take (oldest will be taken, i.e. from the beginning of the file).

    Returns
    -------
    str :
        A string with the path to the new file
    """
    cdo_command = (
        "cdo "
        + " -f nc "
        + " -seltimestep,1/"
        + str(take)
        + " "
        + f
        + " "
        + f.replace(".nc", "_oldest_" + str(take) + "_timesteps.nc")
    )
    click.secho(
        "Selecting oldest %s timesteps for further processing " % str(take), fg="cyan"
    )
    click.secho(cdo_command, fg="cyan")
    subprocess.run(cdo_command, shell=True, check=True)
    return f.replace(".nc", "_oldest_" + str(int) + "_timesteps.nc")


class Scope:
    """
    Base class for various Scope objects. Other classes should extend this one.
    """

    def __init__(self, config: dict, whos_turn: str):
        """
        Parameters
        ----------
        config : dict
            A dictionary (normally recieved from a YAML file) describing the
            ``scope`` configuration. An example dictionary is included in the root
            directory under ``examples/scope_config.yaml``
        whos_turn : str
            An explicit model name telling you which model is currently
            interfacing with ``scope`` e.g. ``echam`` or ``pism``.

        Warning
        -------
        This function has a filesystem side-effect: it generates the couple
        folder defined in ``config["scope"]["couple_dir"]``. If you don't have
        permissions to create this folder, the object initialization will
        fail...


        Some design features are listed below:

        * **``pre`` and ``post`` hooks**
        --------------------------------

        Any appropriately decorated method of a ``scope`` object has a hook to
        call a script with specific arguments and flags before and after the
        main scope method call. Best explained by an example. Assume your Scope
        subclass has a method "send". Here is the order the program will
        execute in, given the following configuration:

        .. code :: yaml

            pre_send:
                program: /some/path/to/an/executable
                args:
                    - list
                    - of
                    - arguments
                flags:
                    - "--flag value1"
                    - "--different_flag value2"

            post_send:
                program: /some/other/path
                args:
                    - A
                    - B
                    - C
                flags:
                    - "--different_flag value3"

        Given this configuration, an idealized system call would look like the
        example shown below. Note however that the Python program calls the
        shell and immediately destroys it again, so any variables exported to
        the environment (probably) don't survive:

        .. code :: shell

            $ ./pre_send['program'] list of arguments --flag value1 --different_flag value2
            $ <... python call to send method ...>
            $ ./post_send['program'] A B C --different_flag value 3

        """
        self.config = config
        self.whos_turn = whos_turn

        try:
            if not os.path.isdir(config["scope"]["couple_dir"]):
                os.makedirs(config["scope"]["couple_dir"])
        except IOError:
            warnings.warn(
                f"Couldn't generate {config['scope']['couple_dir']} folder, this may cause downstream errors..."
            )

    def get_cdo_prefix(self, has_openMP: bool = False):
        """
        Return a string with an appropriate ``cdo`` prefix for using OpenMP
        with the ``-P`` flag.

        Parameters
        ----------
        has_openMP : bool
            Default is ``False``. You can explicitly override the ability of
            ``cdo`` to use the ``-P`` flag. If set to ``True``, the config must
            have an entry under ``config[scope][number openMP processes]``
            defining how many openMP processes to use (should be an int)

        Returns
        -------
        str :
            A string which should be used for the ``cdo`` call, either with or
            without ``-P X``, where ``X`` is the number of openMP processes to
            use.
        """
        if not has_openMP:
            has_openMP = determine_cdo_openMP()
        if has_openMP:
            return "cdo -P " + str(self.config["scope"]["number openMP processes"])
        return "cdo"

    class ScopeDecorators:
        """Contains decorators you can use on class methods"""

        # NOTE(PG): This is a "static method" which takes self as the first
        # argument. That "self" actually referes to the self of the object
        # method which is wrapped, not the "self" of this class.
        @staticmethod
        def _wrap_hook(self, meth, pre_or_post):
            program_to_call = (
                self.config[self.whos_turn]
                .get(f"{pre_or_post}_" + meth.__name__, {})
                .get("program")
            )

            flags_for_program = (
                self.config[self.whos_turn]
                .get(f"{pre_or_post}_" + meth.__name__, {})
                .get("flags_for_program")
            )

            arguments_for_program = (
                self.config[self.whos_turn]
                .get(f"{pre_or_post}_" + meth.__name__, {})
                .get("arguments_for_program")
            )

            if program_to_call:
                full_process = program_to_call
                if flags_for_program:
                    full_process += flags_for_program
                if arguments_for_program:
                    full_process += arguments_for_program
                subprocess.run(full_process, shell=True, check=True)

        # PG: Why is it a classmethod? I don't understand this yet...
        @classmethod
        def pre_hook(cls, meth):
            """Based upon the ``self.config``, runs a specific system command

            Using the method name, you can define

            """
            # Did you ask yourself -- What's wraps? See:
            # https://www.thecodeship.com/patterns/guide-to-python-function-decorators/
            @wraps(meth)
            def wrapped_meth(self, *args):
                self.ScopeDecorators._wrap_hook(self, meth, "pre")
                meth(self, *args)

            return wrapped_meth

        @classmethod
        def post_hook(cls, meth):
            @wraps(meth)
            def wrapped_meth(self, *args):
                meth(self, *args)
                self.ScopeDecorators._wrap_hook(self, meth, "post")

            return wrapped_meth


class Send(Scope):
    """
    Subclass of ``Scope`` which enables sending of models via ``cdo``.
    Use the ``send`` method after building a ``Precprocess`` object.
    """

    @Scope.ScopeDecorators.pre_hook
    @Scope.ScopeDecorators.post_hook
    def send(self):
        """
        Selects and combines variables from various file into one single file for futher processing.

        Files produced:
        ---------------
        * ``<sender_type>_file_for_<reciever_type>`` (e.g. ``atmosphere_file_for_ice.nc``)

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for (sender_type, sender_args) in self._all_senders():
            self.sending_to = sender_type
            # Better handling of files during the loop
            self.combine_list = []
            for variable_name, variable_dict in sender_args.items():
                # Maybe never needed:
                self.current_var_name = variable_name
                self.current_var_dict = variable_dict
                # Insert the first temporary file before transforms at the end
                # of list:
                self._make_tmp_files_for_variable(variable_name, variable_dict)
                # Run CDO commands:
                self._run_cdo_for_variable(variable_name, variable_dict)
                # Possibly rename variables via send_as:
                self._rename_send_as_variables(variable_name, variable_dict)
            logger.debug(
                f"Finished {sender_type} extraction, will combine these files:"
            )
            for f in self.combine_list:
                logger.debug(f"* {f}")
            self._combine_tmp_variable_files(sender_type, self.combine_list)

    def _all_senders(self):
        """
        A generator giving tuples of the *reciever_type* (e.g. ice, atmosphere,
        ocean, solid earth), and the *configuration for the reciever type*,
        including variables and corresponding specifications for which files to
        use and how to process them.


        Example
        -------
        Here is an example for the reciever specification dictionary. See the
        documentation regarding ``scope`` configuration for further
        information:

        .. code::

            temp2:
                files:
                    pattern: "{{ EXP_ID }}_echam6_echam_{{ DATE_PATTERN }}.grb"
                    take:
                        newest: 12
                code_table: "echam6"
            aprl:
                files:
                    dir: "/work/ollie/pgierz/scope_tests/outdata/echam/"
                    pattern: "{{ EXP_ID }}_echam6_echam_{{ DATE_PATTERN }}.grb"
                    take:
                        newest: 12
                code_table: "/work/ollie/pgierz/scope_tests/outdata/echam/PI_1x10_185001.01_echam.codes"

        Yields
        ------
        tuple of (str, dict)

            The first element of the tuple, ``reciever_type``, is a string
            describing what sort of model should get this data; e.g. "ice",
            "atmosphere"

            The second element, ``reciever_spec``, is a dictionary describing
            which files should be used.
        """
        if self.config[self.whos_turn].get("send"):
            for reciever_type in self.config[self.whos_turn].get("send"):
                reciever_spec = self.config[self.whos_turn]["send"][reciever_type]
                yield (reciever_type, reciever_spec)

    def _construct_filelist(self, var_dict):
        """
        Constructs a file list to use for further processing based on user
        specifications.

        Parameters
        ----------
        var_dict : dict
            Configuration dictionary for how to handle one specific variable.

        Returns
        -------
        file_list
            A list of files for further processing.

        Example
        -------
        The variable configuration dictionary can have the following top-level **keys**:

        * ``files`` may contain:
            * a ``filepattern`` in regex to look for
            * ``take`` which files or timesteps to take, either specific, or
              ``newest``/``latest`` followed by an integer.
            * ``dir`` a directory where to look for the files. Note that if
              this is not provided, the default is to fall back to the top level
              ``outdata_dir`` for the currently sending model.
        """
        r = re.compile(var_dict["files"]["pattern"])
        file_directory = var_dict["files"].get(
            "dir", self.config[self.whos_turn].get("outdata_dir")
        )
        logger.debug(f"file pattern = {var_dict['files']['pattern']}")
        logger.debug(f"regex = {r}")
        logger.debug(f"file_directory = {file_directory}")
        all_files = []
        for rootname, _, filenames in os.walk(file_directory):
            for filename in filenames:
                full_name = os.path.join(rootname, filename)
                all_files.append(full_name)
            break  # Do not go into subdirectories
        all_files = sorted(all_files)
        logger.debug("All files:")
        for f in all_files:
            logger.debug(f"* {f}")

        # Just the matching files:
        matching_files = sorted([f for f in all_files if r.match(os.path.basename(f))])
        logger.debug("Matching files:")
        for f in matching_files:
            logger.debug(f"* {f}")
        if "take" in var_dict["files"]:
            if var_dict["files"]["take"].get("what") == "files":
                if "newest" in var_dict["files"]["take"]:
                    take = int(var_dict["files"]["take"]["newest"])
                    return matching_files[-take:]
                if "oldest" in var_dict["files"]["take"]:
                    take = int(var_dict["files"]["take"]["oldest"])
                    return matching_files[:take]
                # FIXME: This is wrong:
                if "specific" in var_dict["files"]["take"]:
                    return var_dict["files"]["take"]["specific"]
                raise SyntaxError("You must specify newest, oldest, or specific!")
            if var_dict["files"]["take"].get("what") == "timesteps":
                if "newest" in var_dict["files"]["take"]:
                    take = int(var_dict["files"]["take"]["newest"])
                    return get_newest_n_timesteps(matching_files[-1], take)
                if "oldest" in var_dict["files"]["take"]:
                    take = int(var_dict["files"]["take"]["oldest"])
                    return get_oldest_n_timesteps(matching_files[-1], take)
                if "specific" in var_dict["files"]["take"]:
                    # return get_specific_timesteps[matching_files[-1], take]
                    raise NotImplementedError(
                        "Get specific timesteps not yet implemented!"
                    )
                raise SyntaxError("You must specify newest, oldest, or specific!")
            logger.error(var_dict)
            raise SyntaxError(
                """
                You specified take in YAML, but didn't specify what to take.
                Please either use 'timesteps' or 'files'
                """
            )
        return matching_files

    def _make_tmp_files_for_variable(self, varname, var_dict):
        """
        Generates temporary files for further processing with ``scope``.

        Given a variable name and a description dictionary of how it should be
        extracted and processed, this method makes a temporary file,
        ``<sender_name>_<varname>_file_for_scope.dat``, e.g.
        ``echam_temp2_file_for_scope.dat`` in the ``couple_dir``.

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

        * ``code_table`` describing which ``GRIB`` code numbers correspond to
          which variables. If not given, the fallback value is the value of
          ``code_table`` in the sender configuration.

        Converts any input file to ``nc`` via `cdo`. Runs both ``select`` and
        ``settable``.

        Returns
        -------
        None

        """
        flist = self._construct_filelist(var_dict)
        logger.debug(f"The following files will be used for: {varname}")
        for f in flist:
            logger.debug(f"- {f}")
        code_table = var_dict.get(
            "code_table", self.config[self.whos_turn].get("code_table")
        )
        code_table_command = f" -t {code_table}" if code_table else ""
        convert_to_netcdf = var_dict.get(
            "convert_to_netcdf",
            self.config[self.whos_turn].get("convert_to_netcdf", True),
        )
        logger.debug(f"{varname} will be converted to netcdf? {convert_to_netcdf}")
        convert_command = " -f nc" if convert_to_netcdf else ""
        ofile = (
            self.config["scope"]["couple_dir"]
            + "/"
            + self.whos_turn
            + "_"
            + varname
            + "_file_for_scope.dat"
        )
        cdo_command = (
            self.get_cdo_prefix()
            + convert_command
            + " "
            + code_table_command
            + " -select,name="
            + varname
            + " "
            + " ".join(flist)
            + " "
            + ofile
        )

        click.secho(
            "Selecting %s for further processing with SCOPE..." % varname, fg="cyan"
        )
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)
        self.combine_list.append(ofile)

    def _run_cdo_for_variable(self, variable_name, variable_dict):
        var_dict = variable_dict
        if "cdo" in variable_dict:
            cdo_commands = variable_dict["cdo"]
            code_table = var_dict.get(
                "code_table", self.config[self.whos_turn].get("code_table")
            )
            code_table_command = f" -t {code_table}" if code_table else ""
            convert_to_netcdf = var_dict.get(
                "convert_to_netcdf",
                self.config[self.whos_turn].get("convert_to_netcdf", True),
            )
            convert_command = " -f nc" if convert_to_netcdf else ""
            try:
                assert isinstance(cdo_commands, list)
            except AssertionError:
                logger.error("ERROR -- you need to have all cdo commands as a list!")
                sys.exit(1)
            original_input = self.combine_list.pop()
            for tmp_file_counter, cdo_command in enumerate(cdo_commands):
                output_file = (
                    self.config["scope"]["couple_dir"]
                    + "/"
                    + self.whos_turn
                    + "_"
                    + variable_name
                    + "_cdo_transform_"
                    + str(tmp_file_counter)
                )
                if tmp_file_counter == 0:
                    input_file = original_input
                else:
                    input_file = (
                        self.config["scope"]["couple_dir"]
                        + "/"
                        + self.whos_turn
                        + "_"
                        + variable_name
                        + "_cdo_transform_"
                        + str(tmp_file_counter - 1)
                    )
                cdo_command = (
                    self.get_cdo_prefix()
                    + convert_command
                    + " "
                    + code_table_command
                    + " "
                    + cdo_command
                    + " "
                    + input_file
                    + " "
                    + output_file
                )
                click.secho(cdo_command, fg="cyan")
                subprocess.run(cdo_command, shell=True, check=True)
            click.secho(
                f"Moving last file {output_file} back to {original_input}", fg="cyan"
            )
            os.rename(output_file, original_input)
            renamed_file = rename_with_suggested_fileext(original_input)
            self.combine_list.append(renamed_file)

    def _rename_send_as_variables(self, variable_name, variable_dict):
        var_dict = variable_dict
        if "send_as" in variable_dict:
            send_as = variable_dict["send_as"]
            code_table = var_dict.get(
                "code_table", self.config[self.whos_turn].get("code_table")
            )
            code_table_command = f" -t {code_table}" if code_table else ""
            convert_to_netcdf = var_dict.get(
                "convert_to_netcdf",
                self.config[self.whos_turn].get("convert_to_netcdf", True),
            )
            convert_command = " -f nc" if convert_to_netcdf else ""
            fin = self.combine_list.pop()
            if (
                "netcdf" not in determine_fileextension(fin).lower()
                and not convert_to_netcdf
            ):
                logger.error("You gave a {determine_fileextension(fin).lower()} file")
                logger.error(
                    "Sorry, renaming with >>send as<< does not work for non-netcdf files, as internal metadata is not preserved!"
                )
                return fin
            fout = (
                self.config["scope"]["couple_dir"]
                + "/"
                + self.whos_turn
                + "_"
                + variable_name
                + "_file_for_scope_send_as_"
                + send_as
                + ".nc"
            )
            cdo_command = (
                self.get_cdo_prefix()
                + convert_command
                + " "
                + code_table_command
                + " "
                + f"chname,{variable_name},{send_as} {fin} {fout}"
            )
            click.secho(cdo_command, fg="cyan")
            subprocess.run(cdo_command, shell=True, check=True)
            click.secho(
                f"Moving renamed variable in file {fout} back to {fin}", fg="cyan"
            )
            os.rename(fout, fin)
            self.combine_list.append(fin)
            return fin

    # TODO/FIXME: This function does not work correctly if there are different
    # time axis for each variable. It might be better to just leave each
    # variable in it's own file.
    def _combine_tmp_variable_files(self, reciever_type, files_to_combine):
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

        Notes
        -----
        This executes a ``cdo merge`` command to concatenate all files found which
        should be sent to particular model.
        """
        logger.debug(reciever_type)
        output_file = os.path.join(
            self.config["scope"]["couple_dir"],
            self.config[self.whos_turn]["type"] + "_file_for_" + reciever_type + ".dat",
        )
        cdo_command = (
            self.get_cdo_prefix()
            + " merge "
            + " ".join(files_to_combine)
            + " "
            + output_file
        )
        # TODO: Add expressions
        click.secho("Combine files for sending to %s" % reciever_type, fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)


class Recieve(Scope):
    def _calculate_weights(self, model, type_, interp):
        regrid_weight_file = os.path.join(
            self.config["scope"]["couple_dir"],
            "_".join([self.config[model]["type"], type_, interp, "weight_file.nc"]),
        )

        cdo_command = (
            self.get_cdo_prefix()
            + " gen"
            + interp
            + ","
            + self.config[model]["griddes"]
            + " "
            + self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_file_for_"
            + self.config[model]["type"]
            + ".dat"
            + " "
            + regrid_weight_file
        )

        if not os.path.isfile(regrid_weight_file):
            click.secho("Calculating weights: ", fg="cyan")
            click.secho(cdo_command, fg="cyan")
            subprocess.run(cdo_command, shell=True, check=True)
        return regrid_weight_file

    def recieve(self):
        if self.config[self.whos_turn].get("recieve"):
            for sender_type in self.config[self.whos_turn].get("recieve"):
                self.combine_lists = {}
                if self.config[self.whos_turn]["recieve"].get(sender_type):
                    for variable in self.config[self.whos_turn]["recieve"].get(
                        sender_type
                    ):
                        model = self.whos_turn
                        type_ = sender_type
                        target_file = (
                            self.config[self.whos_turn]
                            .get("recieve")
                            .get(sender_type)
                            .get(variable)
                            .get("target_file")
                        )
                        self.combine_lists.setdefault(target_file, [])
                        interp = (
                            self.config[self.whos_turn]
                            .get("recieve")
                            .get(sender_type)
                            .get(variable)
                            .get("interp")
                        )
                        if "receive_from" in self.config[self.whos_turn].get(
                            "recieve"
                        ).get(sender_type).get(variable):
                            recv_from = (
                                self.config[self.whos_turn]
                                .get("recieve")
                                .get(sender_type)
                                .get(variable)
                                .get("receive_from")
                            )
                            self.regrid_recieve_from(
                                model, type_, interp, variable, target_file, recv_from
                            )
                        else:
                            self.regrid_one_var(
                                model, type_, interp, variable, target_file
                            )
                        # Run CDOs:
                        if "cdo" in self.config[self.whos_turn].get("recieve").get(
                            sender_type
                        ).get(variable):
                            cdo_commands = (
                                self.config[self.whos_turn]
                                .get("recieve")
                                .get(sender_type)
                                .get(variable)
                                .get("cdo")
                            )
                            self.run_cdos(
                                model, type_, variable, target_file, cdo_commands
                            )
                logger.debug(f"Files to be merged for {sender_type}:")
                for target_file in self.combine_lists:
                    logger.debug(target_file)
                    for f in self.combine_lists[target_file]:
                        logger.debug(f"* {f}")
                    self._combine_tmp_variable_files(
                        target_file, self.combine_lists[target_file]
                    )

    def _combine_tmp_variable_files(self, target_file, source_files):
        output_file = target_file
        cdo_command = (
            self.get_cdo_prefix()
            + " merge "
            + " ".join(source_files)
            + " "
            + output_file
        )
        click.secho("Combine files after processing")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)

    def run_cdos(self, model, type_, variable, target_file, cdo_commands):
        original_ifile = self.combine_lists[target_file].pop()
        file_stub = original_ifile.replace(".dat", "_")
        for command_counter, command in enumerate(cdo_commands):
            logger.debug(f"command_counter={command_counter}")
            logger.debug(f"command={command}")
            ofile = file_stub + str(command_counter) + ".dat"
            if command_counter == 0:
                ifile = original_ifile
            else:
                ifile = file_stub + str(command_counter - 1) + ".dat"
            cdo_command = (
                self.get_cdo_prefix() + " " + command + " " + ifile + " " + ofile
            )
            click.secho(cdo_command, fg="cyan")
            subprocess.run(cdo_command, shell=True, check=True)
        # Move back to original infile:
        os.rename(ofile, original_ifile)
        self.combine_lists[target_file].append(original_ifile)

    def regrid_recieve_from(
        self, model, type_, interp, variable, target_file, recv_from
    ):
        weight_file = self._calculate_weights(model, type_, interp)
        cdo_command = (
            self.get_cdo_prefix()
            + " remap,"
            + self.config[model]["griddes"]
            + ","
            + weight_file
            + " "
            + "-selvar,"
            + ",".join(recv_from)
            + " "
            + self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_file_for_"
            + self.config[model]["type"]
            + ".dat "
            + self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_"
            + variable
            + "_for_"
            + self.config[model]["type"]
            + "_on_"
            + self.config[model]["type"]
            + "_grid.dat"
        )
        click.secho("Remapping (with recieve_from): ", fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)
        self.combine_lists[target_file].append(
            self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_"
            + variable
            + "_for_"
            + self.config[model]["type"]
            + "_on_"
            + self.config[model]["type"]
            + "_grid.dat"
        )

    def regrid_one_var(self, model, type_, interp, variable, target_file):
        weight_file = self._calculate_weights(model, type_, interp)
        cdo_command = (
            self.get_cdo_prefix()
            + " remap,"
            + self.config[model]["griddes"]
            + ","
            + weight_file
            + " "
            + "-selvar,"
            + variable
            + " "
            + self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_file_for_"
            + self.config[model]["type"]
            + ".dat "
            + self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_"
            + variable
            + "_for_"
            + self.config[model]["type"]
            + "_on_"
            + self.config[model]["type"]
            + "_grid.dat"
        )
        click.secho("Remapping: ", fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)
        self.combine_lists[target_file].append(
            self.config["scope"]["couple_dir"]
            + "/"
            + type_
            + "_"
            + variable
            + "_for_"
            + self.config[model]["type"]
            + "_on_"
            + self.config[model]["type"]
            + "_grid.dat"
        )


# -*- coding: utf-8 -*-
# -*- last line -*-
