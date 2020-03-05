SCOPE Documentation
===================

Welcome to the ``scope`` documentation. ``scope`` is a two-in-one command line
utility as well as a Python library designed to facilitate coupling and
communication between various Earth system models. The minimal quickstart::

    $ pip install scope-coupler
    $ scope --help
    $ scope preprocess ${CONFIG_FILE} echam
    $ scope regrid ${CONFIG_FILE} pism

The commands listed above would install the scope coupler; show you what it can
do, gather relevant files from the atmosphere model ``echam``, and regrid them
onto a ``pism`` ice sheet grid.

However, ``scope`` is capable of much more than this. You can preprocess or
postprocess data on either side of the communication, modify variable names and
attributes, perform corrections due to resolution differences, and provide your
own specific steps for each part of the coupling process.

``scope`` is designed to run completely independently of the models being used,
the run-time infrastructure available on the supercomputer, and, perhaps most
importantly **requires 0 modifications to your model code**. To get started,
have a look at the documentation below.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   usage
   API
   contributing
   authors
   history

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
