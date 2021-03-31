import os
import re
import sys
import copy
import glob
import operator
import subprocess

import click
from tabulate import tabulate

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
@click.option("tsort",
              "--tsort",
              envvar="APPFIND_TOKEN_SORT",
              multiple=True,
              type=click.Path(),
              help="""This optional field specifies the order preference in which
              tokens will be used to sort versions. Can be passed via the
              APPFIND_TOKEN_SORT environment variable. This can be useful if an
              app developer decides to change thier versioning from {{major}}.{{minor}}
              to {{year}}.{{month}}. If you wanted the {{year}}.{{month}} scheme
              to be the latest, you would set the it to something like this:\n
              'year:month:major:minor'
              If this option is not used, sorting will default to version name.
              """.format(os.pathsep)
              )
@click.pass_context
###############################################################################
# Main entry point
###############################################################################
def cli(ctx, templates, prtokens, tsort):
    """A universal app finder and wrapper. Finds multiple versions of the same
    application on disk from using provided templates. Launches the latest
    version of the application by default."""

    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    # if not templates:
    #     click.echo(f"No path templates found.")
    #     return

    matches = _glob_and_match(click, templates, prtokens, tsort)

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

    match = next((x for x in matches if appver in (x.get('tags') if x.get('tags') else [])), None)
    if not match:
        match = next((x for x in matches if x['version'] == appver), None)
    elif not match:
        raise click.ClickException(f"No version found matching '{appver}'")

    extra_args = click.get_current_context().args

    if apphelp:
        extra_args.insert(0, "--help")

    cmd = [match['path']]

    if extra_args:
        cmd.extend(extra_args)

    click.echo(f"Launching: {' '.join(cmd)}")
    subprocess.call(cmd)


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

    matches = ctx.obj["matches"]

    tags_col = [", ".join(m["tags"]) if m.get("tags") else None for m in matches]
    versions_col = [m["version"] for m in matches]
    paths_col = [m["path"] for m in matches]

    table_dict = {"tags": tags_col, "version": versions_col}
    if paths:
        table_dict["path"] = paths_col

    click.echo(tabulate(table_dict, headers="keys"))


def _glob_and_match(click, templates, prtokens, tsort):

    tokens = []  # this will be a list of all the tokens found in the templates
    tdicts = []  # a list of dicts with template information
    app_matches = []

    for template in templates:

        if "[" in template and "]" in template:
            version_regex = re.compile(r".*\[(?P<version>.*)\].*")
            match = version_regex.match(template)
            tversion = match.group('version')
            tpath = template.replace("[", "").replace("]", "")
            tpath = os.path.abspath(os.path.expanduser(tpath))
        else:
            raise click.ClickException("Error: must capture the version string in the template with brackets!")

        tdict = {"tpath": tpath, "tversion": tversion}
        tdicts.append(tdict)

        token_regex = re.compile(r"\{([a-z]*)\}")
        token_matches = token_regex.findall(template)
        tokens = tokens + list(set(token_matches) - set(tokens))

    # print(tokens)
    # print(tdicts)

    app_match_template = {tk: int(0) for tk in tokens}
    # print(app_match_template)
    app_matches = []

    for tdict in tdicts:

        glob_pattern = _format(
            tdict["tpath"], dict((key, "*") for key in tokens)
        )

        globs = glob.glob(glob_pattern)
        # print(globs)

        # tdict["globs"] = globs

        exec_regex_pattern = _format(
            tdict["tpath"],
            # Put () around the provided expressions so that they become capture groups.
            dict(
                (key, [r"(?P=%s)" % key, r"(?P<%s>\d+)" % key]) for key in tokens
            ),
        )

        # accumulate the software version objects to return. this will include
        # include the head/tail anchors in the regex
        exec_regex_pattern = "^%s$" % (exec_regex_pattern,)
        # print(exec_regex_pattern)

        # compile the regex
        exec_regex = re.compile(exec_regex_pattern, re.IGNORECASE)
        # print(exec_regex)

        # tdict["exec_regex"] = exec_regex

        # print(tdict)
        # iterate over each executable found for the glob pattern and find
        # matched components via the regex
        for glob_path in globs:

            # print(glob_path)
            match = exec_regex.match(glob_path)
            # print(match)
            if not match:
                continue

            token_matches = match.groupdict()  # get a dict of all token matches
            token_matches = {k: int(v) for k, v in token_matches.items()}
            version = tdict["tversion"].format(**token_matches)  # create the version

            app_match = copy.copy(app_match_template)
            app_match['path'] = glob_path
            app_match['version'] = version
            app_match.update(token_matches)
            app_matches.append(app_match)

    if app_matches and tsort:
        app_matches = sorted(app_matches, key=operator.itemgetter(*tsort), reverse=True)
    elif app_matches:
        app_matches = sorted(app_matches, key=operator.itemgetter('version'), reverse=True)

    found_latest = False
    prtokens = list(prtokens)
    for app_match in app_matches:
        if found_latest and not prtokens:
            break
        app_match["tags"] = []
        # tag the version item that doesnt have a prtoken as latest
        if not found_latest and not any(x in prtokens for x in [k for k, v in app_match.items() if v is not 0]):
            app_match["tags"].append('latest')
            found_latest = True
        # tag the fist versions we find with a prtoken
        for prtoken in [k for k, v in app_match.items() if (v is not 0 and k in prtokens)]:
            app_match["tags"].append(prtoken)
            prtokens.pop(prtokens.index(prtoken))

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
