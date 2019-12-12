# -*- coding: utf-8 -*-
"""
Here, the ``scope`` library is described. This allows you to use specific parts
of ``scope`` from other programs.

``scope`` consists of several main classes. Note that most of them provide
Python access to ``cdo`` calls via Python's built-in ``subprocess`` module.
Without a correctly installed ``cdo``, many of these functions/classes will not
work.


Here, we provide a quick summary, but please look at the documentation for each
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

* ``Preprocess`` -- a class to extract and combine various NetCDF files for
  further processing.

* ``Regrid`` -- a class to easily regrid from one model to another, depending
  on the specifications in the ``scope_config.yaml``
"""

from functools import wraps
import logging
import os
import re
import subprocess

import click


def determine_cdo_openMP():
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


class Scope(object):
    def __init__(self, config, whos_turn):
        """
        Base class for various Scope objects. Other classes should extend this one.

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
        subclass has a method "preprocess". Here is the order the program will
        execute in, given the following configuration:

        .. code :: yaml

            pre_preprocess:
                program: /some/path/to/an/executable
                args:
                    - list
                    - of
                    - arguments
                flags:
                    - "--flag value1"
                    - "--different_flag value2"

            post_preprocess:
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

            $ ./pre_preprocess['program'] list of arguments --flag value1 --different_flag value2
            $ <... python call to preprocess method ...>
            $ ./post_preprocess['program'] A B C --different_flag value 3

        """
        self.config = config
        self.whos_turn = whos_turn

        if not os.path.isdir(config["scope"]["couple_dir"]):
            os.makedirs(config["scope"]["couple_dir"])

    def get_cdo_prefix(self, has_openMP=None):
        """
        Return a string with an appropriate ``cdo`` prefix for using OpenMP
        with the ``-P`` flag.

        Parameters
        ----------
        has_openMP : bool
            Default is ``None``. You can explicitly override the ability of
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
        else:
            return "cdo"

    class ScopeDecorators(object):
        """Contains decorators you can use on class methods"""

        # FIXME: I don't really like that this is exactly the same above with
        # only a positional change. Probably it can abstracted away...
        @staticmethod
        def _wrap_hook(self, meth):
            program_to_call = self.config[self.whos_turn].get("pre_" + meth.__name__, {}).get("program")

            flags_for_program = self.config[self.whos_turn].get("pre_" + meth.__name__, {}).get("flags_for_program")

            arguments_for_program = (
                self.config[self.whos_turn].get("pre_" + meth.__name__, {}).get("arguments_for_program")
            )

            full_process = program_to_call
            if flags_for_program:
                full_process += flags_for_program
            if arguments_for_program:
                full_process += arguments_for_program
            subprocess.run(full_process, shell=True, check=True)

        # PG: Why is it a classmethod? I don't understand this yet...
        @classmethod
        def pre_hook(cls, meth):
            """ Based upon the ``self.config``, runs a specific system command

            Using the method name, you can define

            """
            # Did you ask yourself -- What's wraps? See:
            # https://www.thecodeship.com/patterns/guide-to-python-function-decorators/
            @wraps(meth)
            def wrapped_meth(self, *args):
                self._wrap_hook(self, meth)
                meth(self, *args)

            return wrapped_meth

        @classmethod
        def post_hook(cls, meth):
            @wraps(meth)
            def wrapped_meth(self, *args):
                meth(*args)
                self._wrap_hook(self, meth)

            return wrapped_meth


class Preprocess(Scope):
    """
    Subclass of ``Scope`` which enables preprocessing of models via ``cdo``.
    Use the ``preprocess`` method after building a ``Precprocess`` object.
    """

    @Scope.ScopeDecorators.pre_hook
    @Scope.ScopeDecorators.post_hook
    def preprocess(self):
        for (sender_type, sender_args) in self._all_senders():
            for variable_name, variable_dict in sender_args.items():
                logging.debug("The following files will be used for:", variable_name)
                self._make_tmp_files_for_variable(variable_name, variable_dict)
            self._combine_tmp_variable_files(sender_type)

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
                code table: "echam6"
            aprl:
                files:
                    dir: "/work/ollie/pgierz/scope_tests/outdata/echam/"
                    pattern: "{{ EXP_ID }}_echam6_echam_{{ DATE_PATTERN }}.grb"
                    take:
                        newest: 12
                code table: "/work/ollie/pgierz/scope_tests/outdata/echam/PI_1x10_185001.01_echam.codes"

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
        file_directory = var_dict["files"].get("dir", self.config[self.whos_turn].get("outdata_dir"))

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

        Converts any input file to ``nc`` via `cdo`. Runs both ``select`` and
        ``settable``.

        Returns
        -------
        None

        """
        flist = self._construct_filelist(var_dict)
        for f in flist:
            print("- ", f)
        code_table = var_dict.get("code table", self.config[self.whos_turn].get("code table"))
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

        click.secho("Selecting %s for further processing with SCOPE..." % varname, fg="cyan")
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

        Notes
        -----
        This executes a ``cdo mergetime`` command to concatenate all files found which
        should be sent to particular model.
        """
        print(reciever_type)
        reciever = self.config.get(self.whos_turn, {}).get("send", {}).get(reciever_type, {})
        variables_to_send_to_reciever = list(reciever)
        files_to_combine = []
        for f in os.listdir(self.config["scope"]["couple_dir"]):
            fvar = f.replace(self.whos_turn + "_", "").replace("_file_for_scope.nc", "")
            if fvar in variables_to_send_to_reciever:
                files_to_combine.append(os.path.join(self.config["scope"]["couple_dir"], f))
        output_file = os.path.join(
            self.config["scope"]["couple_dir"],
            self.config[self.whos_turn]["type"] + "_file_for_" + reciever_type + ".nc",
        )
        cdo_command = self.get_cdo_prefix() + " mergetime " + " ".join(files_to_combine) + " " + output_file
        click.secho("Combine files for sending to %s" % reciever_type, fg="cyan")
        click.secho(cdo_command, fg="cyan")
        subprocess.run(cdo_command, shell=True, check=True)


class Regrid(Scope):
    def _calculate_weights(self, Model, Type, Interp):
        regrid_weight_file = os.path.join(
            self.config["scope"]["couple_dir"], "_".join([self.config[Model]["type"], Type, Interp, "weight_file.nc"])
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
                    for Variable in self.config[self.whos_turn]["recieve"].get(sender_type):
                        Model = self.whos_turn
                        Type = sender_type
                        Interp = self.config[self.whos_turn].get("recieve").get(sender_type).get(Variable).get("interp")
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
