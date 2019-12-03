# -*- coding: utf-8 -*-

"""Console script for scope."""
import sys
import click
import yaml

import jinja2

from scope import Regrid, Preprocess


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
                yaml_contents = yaml_file.read()
                # Open the template
                template = jinja2.Template(yaml_contents)
                # Parse the template from YAML to a dict
                preparsed_dict = yaml.load(yaml_contents, Loader=yaml.FullLoader)
                #
                outputText = template.render(**preparsed_dict["template_replacements"])
                parsed_dict = yaml.load(outputText)
                del parsed_dict["template_replacements"]
                return parsed_dict
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
@click.argument("whos_turn")
def regrid(config_path, whos_turn):
    config = yaml_file_to_dict(config_path)
    regridder = Regrid(config, whos_turn)
    regridder.regrid()


@main.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.argument("whos_turn")
def preprocess(config_path, whos_turn):
    config = yaml_file_to_dict(config_path)

    print(80 * "-")
    import pprint

    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(config)
    print(80 * "-")

    preprocessor = Preprocess(config, whos_turn)
    preprocessor.preprocess()

if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
