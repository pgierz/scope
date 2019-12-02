# -*- coding: utf-8 -*-

"""Console script for scope."""
import sys
import click
import yaml

from scope import Regrid


YAML_AUTO_EXTENSIONS = ["", ".yml", ".yaml", ".YML", ".YAML"]


def yaml_file_to_dict(filepath):
    """
    Given a yaml file, returns a corresponding dictionary.

    If you do not give an extension, tries again after appending one.

    Parameters
    ----------
    filepath : str
        Where to get the YAML file from

    Returns
    -------
    dict
        A dictionary representation of the yaml file.
    """
    for extension in YAML_AUTO_EXTENSIONS:
        try:
            with open(filepath + extension) as yaml_file:
                return yaml.load(yaml_file, Loader=yaml.FullLoader)
        except IOError as error:
            logger.debug(
                "IOError (%s) File not found with %s, trying another extension pattern.",
                error.errno,
                filepath + extension,
            )
    raise FileNotFoundError(
        "All file extensions tried and none worked for %s" % filepath
    )


@click.group()
@click.version_option()
def main(args=None):
    """Console script for scope."""
    click.echo("Replace this message by putting your code into scope.cli.main")
    click.echo("See click documentation at http://click.pocoo.org/")
    return 0


@main.command()
@click.argument("config_path", type=click.Path(exists=True))
def regrid(config_path):
    config = yaml_file_to_dict(config_path)
    regridder = Regrid(config, "pism")
    regridder.regrid()


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
