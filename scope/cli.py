# -*- coding: utf-8 -*-

"""Console script for scope."""

import logging
import sys

import click
import yaml
import jinja2

from scope import Recieve, Send


YAML_AUTO_EXTENSIONS = ["", ".yml", ".yaml", ".YML", ".YAML"]


def yaml_file_to_dict(filepath: str) -> dict:
    """
    Given a scope configuration yaml file, returns a corresponding dictionary.

    If you do not give an extension, tries again after appending one:

    + ``.yml``
    + ``.yaml``
    + ``.YML``
    + ``.YAML``

    Note that this function also uses `~jinja2` to replace any templated
    variables found in the under the top-level key ``template_replacements``.
    This key is then deleted from the remainder of the dictionary.

    Parameters
    ----------
    filepath : str
        Where to get the YAML file from

    Returns
    -------
    dict
        A dictionary representation of the yaml file.

    Raises
    ------
    ``OSError`` if the file cannot be found.
    """
    for extension in YAML_AUTO_EXTENSIONS:
        try:
            with open(filepath + extension) as yaml_file:
                yaml_contents = yaml_file.read()
                # Open the template
                template = jinja2.Template(yaml_contents)
                # Parse the template from YAML to a dict
                preparsed_dict = yaml.load(yaml_contents, Loader=yaml.FullLoader)
                #
                outputText = template.render(**preparsed_dict["template_replacements"])
                parsed_dict = yaml.load(outputText, Loader=yaml.FullLoader)
                del parsed_dict["template_replacements"]
                return parsed_dict
        except IOError as error:
            logging.debug(
                "IOError (%s) File not found with %s, trying another extension pattern.",
                error.errno,
                filepath + extension,
            )
    raise OSError("All file extensions tried and none worked for %s" % filepath)


@click.group()
@click.version_option()
def main(args=None):
    """Console script for scope."""
    click.echo(
        "SCOPE a stand-alone coupler. Please use --help for available operations."
    )
    return 0


@main.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.argument("whos_turn")
def recieve(config_path: str, whos_turn: str) -> None:
    """Command line interface to regridding"""
    config = yaml_file_to_dict(config_path)
    reciever = Recieve(config, whos_turn)
    reciever.recieve()


@main.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.argument("whos_turn")
def send(config_path: str, whos_turn: str) -> None:
    config = yaml_file_to_dict(config_path)
    sender = Send(config, whos_turn)
    sender.send()


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
