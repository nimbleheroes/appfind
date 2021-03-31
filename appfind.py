import os
import re
import sys
import glob
import operator
import subprocess

import click
from click_default_group import DefaultGroup


@click.group(cls=DefaultGroup,
             invoke_without_command=True,
             default_if_no_args=True
             )
@click.option("templates",
              "--templates",
              envvar="APPFIND_TEMPLATES",
              multiple=True,
              type=click.Path(),
              required=True,
              help="""Path templates to executable files. Typically passed via the
                   APPFIND_TEMPLATES environment variable. Multiple templates
                   can be separated with a '{0}'. Path templates should contain
                   token names in place of integers in the form of '{{token}}'.
                   Example:\n
                   'path/to/appFolder[{{major}}.{{minor}}.{{release}}]/appExecutable{{major}}.{{minor}}.{{release}}'\n
                   Notice that brackets '[]' surround the first occurance of the
                   full version name. This defines version template and it is required.
                   """.format(os.pathsep)
              )
@click.option("prtokens",
              "--prtokens",
              envvar="APPFIND_PR_TOKENS",
              multiple=True,
              type=click.Path(),
              help="""Specifies the names of 'pre-release' tokens in the path templates.
                   Can be passed via the APPFIND_PR_TOKENS environment variable.
                   The existence of this token in an excecutable match would identify
                   'pre-release' versions of software so they don't launch as
                   the default even if its the latest version. You can specify
                   multiple tokens using a '{0}'. Example:\n
                   'alpha:beta:dev'
                   """.format(os.pathsep)
              )
@click.pass_context
###############################################################################
# Main entry point
###############################################################################
def cli(ctx, templates, prtokens):
    """A universal app finder and wrapper. Finds multiple versions of the same
    application on disk from using provided templates. Launches the latest
    version of the application by default."""

    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    # if not templates:
    #     click.echo(f"No path templates found.")
    #     return

    matches = _glob_and_match(templates, prtokens)

    if not matches:
        raise click.ClickException("No executables found matching templates.")

    ctx.obj['matches'] = matches
    ctx.obj['prtokens'] = prtokens


@cli.command("launch",
             default=True,  # marks this as the default command
             short_help='launch the found app, latest by default',
             context_settings={"ignore_unknown_options": True,
                               "allow_extra_args": True}
             )
@click.option("appver",
              "--appver",
              default="latest",
              help="""Version of the wrapped app to run. You can use
                   'list' command to see all versions available. By default this
                   is set to 'latest' which launches the highest release version. If
                   you've defined pre-release tokens, you can use the name of
                   the token like 'beta' to run the latest version with
                   that token.
                   """
              )
@click.option("apphelp",
              "--apphelp",
              is_flag=True,
              help="Passes the --help flag to the wrapped app.")
@click.pass_context
###############################################################################
# Launch command (default)
###############################################################################
def launch_command(ctx, appver, apphelp):
    """Launches the executable found by appfind. This is the default command
    and will be invoked when no command is passed to appfind. By default,
    this command will will launch the 'latest' non-prerelease version of the
    application."""

    matches = ctx.obj["matches"]

    if appver == "latest":
        match = matches[0]
    elif appver:
        match = next((x for x in matches if x['version'] == appver), None)
        if not match:
            raise click.ClickException(f"No version found matching {appver}")

    extra_args = click.get_current_context().args

    if apphelp:
        extra_args.insert(0, "--help")
    # if extra_args and apphelp:
    #     extra_args.insert(0, "--help")
    # elif not extra_args and apphelp:
    #     extra_args = ["--help"]

    cmd = [match['exec_path']]

    if extra_args:
        cmd.extend(extra_args)

    click.echo(f"Command: {cmd}")
    # subprocess.call(cmd)


@cli.command("list",
             short_help='list the found versions'
             )
@click.option("paths",
              "--paths",
              is_flag=True,
              help="Lists the full executable paths",
              )
@click.pass_context
###############################################################################
# List command
###############################################################################
def list_command(ctx, paths):
    """Lists the versions found by appfind."""
    # click.echo(ctx.obj)
    matches = ctx.obj["matches"]

    for match in matches:
        if paths:
            click.echo(match["exec_path"])
        else:
            click.echo(match["version"])


def _glob_and_match(templates, prtokens):

    app_matches = []

    for template in templates:

        if "[" in template and "]" in template:
            version_regex = re.compile(r".*\[(?P<version>.*)\].*")
            match = version_regex.match(template)
            ver_template = match.group('version')
            template = template.replace("[", "").replace("]", "")
            template = os.path.abspath(os.path.expanduser(template))
        else:
            print("Error: must capture the version string in the template with brackets!")

        token_regex = re.compile(r"\{([a-z]*)\}")
        token_matches = token_regex.findall(template)
        tokens = list(set(token_matches))

        glob_pattern = _format(
            template, dict((key, "*") for key in tokens)
        )

        # print(glob_pattern)
        matching_paths = glob.glob(glob_pattern)
        # print(matching_paths)

        exec_regex_pattern = _format(
            template,
            # Put () around the provided expressions so that they become capture groups.
            dict(
                (key, [r"(?P=%s)" % key, r"(?P<%s>\d+)" % key]) for key in tokens
            ),
        )

        # accumulate the software version objects to return. this will include
        # include the head/tail anchors in the regex
        exec_regex_pattern = "^%s$" % (exec_regex_pattern,)
        # print(regex_pattern)

        # compile the regex
        exec_regex = re.compile(exec_regex_pattern, re.IGNORECASE)
        # print(exec_regex)

        # iterate over each executable found for the glob pattern and find
        # matched components via the regex
        for matching_path in matching_paths:

            match = exec_regex.match(matching_path)

            if not match:
                continue

            app_match = {'exec_path': matching_path}

            token_matches = match.groupdict()
            version = ver_template.format(**token_matches)
            token_matches['version'] = version

            app_match.update(token_matches)
            app_matches.append(app_match)

    if app_matches:
        # app_matches = sorted(app_matches, key=operator.itemgetter('year', 'major'), reverse=True)
        app_matches = sorted(app_matches, key=operator.itemgetter('version'), reverse=True)

    return app_matches


def _format(template, tokens):
    """
    Limited implementation of Python 2.6-like str.format.

    :param str template: String using {<name>} tokens for substitution.
    :param dict tokens: Dictionary of <name> to substitute for <value>.

    :returns: The substituted string, when "<name>" will yield "<value>".
    """
    for key, value in tokens.items():
        if isinstance(value, list):
            template = template.replace("{%s}" % key, value[0]).replace(value[0], value[1], 1)
        else:
            template = template.replace("{%s}" % key, value)

    return template
