===========
Using SCOPE
===========

``scope`` uses configuration files, generally written in the ``YAML`` syntax,
to define what you wantt it do. This configuration is divided into seperate
sections. Here, we give a brief overview. A complete reference is currently
being written.


The first section, simply titled ``scope``, defines general parameters for the program:

.. code-block:: yaml
    :linenos:

    scope:
        couple_dir: "/path/to/directory/"
        number openMP processes: 8

In the example above, we define two things for the program.
    ``couple_dir``
        Line 2

        This entry defines where scope will save it's files. These files
        generally include remap weights to be reused each time the coupler is
        called; gathered output files for processing for the other model; and
        intermediate files that may be interesting for diagnosis.
    ``number openMP processes``
        Line 3

        Since ``scope`` uses ``cdo`` in the background; you can use this to
        define how many processes you want to run ``cdo`` on. This generally
        speeds up regridding.

Next, there is a section which may optionally be defined,
``template_replacements``. Here, you can store key/value pairs which will be
replaced elsewhere in the configuration. As an example:

.. code-block:: yaml
    :linenos:

    template_replacements:
        EXP_ID: "PI_1x10"
        DATE_PATTERN: "[0-9]{6}"

Now, any other time that ``{{ EXP_ID }}`` is used in the configuration, it will
be replaced with ``PI_1x10``. The syntax here is derived from the Jinja2 Python
package used for templating.

.. warning::
    I'm not sure what happens here if you try to use recursion in the template
    replacements!

You can also see in this section that you can define a ``DATE_PATTERN``.
Specific key/value pairs ending with the substring ``PATTERN`` are treated as a
regular expression.

Next, you describe the models you wish to couple together.

.. code-block:: yaml
    :linenos:

    model_name:
        type: physical_domain
        griddes: built-in CDO grid description, or path to a SCRIP formatted file
        outdata_dir: /some/path
        code table: build-in CDO code table, or path to a file with GRB-style code table
        send:
            ...send directives...
        receive:
            ...receive directives...
        pre_step:
            ...description of pre step...
        post_step:
            ...description of post step...


In the generalised example above, we define:

    ``model_name``
         A model to couple, in this case, ``model_name``. Usually, this would be
         more specific, e.g. ``echam``, ``openifs``, ``pism``, ``fesom``.


Inside the ``model_name`` configuration, we again have:

    ``type``
        This describes the *type* of the model; e.g. atmosphere, ice, ocean.
    ``griddes``
        Here, you must specify which grid description to use for this model.
        This is the default for this model.
    ``outdata_dir``
        This defines where scope will, by default, look for files for this
        particular model. However, you can override this on a case by case
        basis. See the send directives for more information.
    ``code_table``
        Since ``scope`` is built on top of ``cdo``, which supports ``grb``
        files, here you can specify which code table to use in order to detect
        variable names when converting from ``grb`` to ``netcdf``.
    ``send``
        This configuration contains send directives for other coupling partners.
        More on this in the next section.
    ``receive``
        This configuration is used to receive information from other models.
    ``pre_step``
        Programs run before a particular step. Can be configured for each step
        separately, e.g. ``pre_preprocess``, or ``pre_regrid``.
    ``post_step``
        Programs run after a particular step


Example: Configuration Files for ``SCOPE``
------------------------------------------

A complete example configuration file is provided under
``examples/scope_config.yaml``:

.. literalinclude:: ../examples/scope_config.yaml
    :language: yaml
    :linenos:


Example: ``PISM`` to ``ECHAM6``
-------------------------------


Command line interface
----------------------

``scope`` comes with a command line interface. For a very quick introduction::

    $ scope --help

This will print usage information.


Any ``scope`` commands you normally would run in a batch job can also be
individually targeted via command line arguments. In principle, the command
structure is always the same, namely::

    $ scope <command> ${CONFIG} ${WHOS_TURN}

This allows you to run one specific part of ``scope`` for a particular
configuration assuming a particular model is currently doing something. As an
example, this could take the form of::

    $ scope preprocess ~/Code/scope/examples/scope_config.yaml echam

This would cause ``scope`` to run the prepare steps described for ``echam``; in
this particular case gathering output files, extracting variables, and placing
the resulting file into the couple folder described in the configuration file.
Note that also and pre- and post-processing hooks defined in the configuration
file will also be run at this point.

All available commands are printed via ``scope --help``.

Currently, the following commands are implemented:

* ``preprocess``
* ``regrid``



Python Library Usage
--------------------

While the command line interface is nice for users who never want to actually
touch ``scope`` code; we also support the ability to use scope functions in
your own ``Python`` programs. this section describes how to use ``scope`` from
a script.

To use scope in a project::

    import scope

Consider having a look at the developer API for more detailed usage.
