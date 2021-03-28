import os
import re
import sys
import glob
import operator

import click

__CONTEXT_SETTINGS = {
    "ignore_unknown_options": True,
    "allow_extra_args": True,
    "help_option_names": ["--help-wrapper"],
}


@click.command(context_settings=__CONTEXT_SETTINGS)
@click.option("--run-version", default="latest", help="Version of this application to run.")
@click.option("--list-versions", is_flag=True, help="Lists all available versions.")
def main(run_version, list_versions):

    exec_templates_str = os.getenv("APPWRAP_EXEC_TEMPLATES")

    if not exec_templates_str:
        click.echo("No APPWRAP_EXEC_TEMPLATES have been defined.")
    else:
        if os.pathsep in exec_templates_str:
            exec_templates = exec_templates_str.split(os.pathsep)
        else:
            exec_templates = [exec_templates_str]

        matches = glob_and_match(exec_templates)
        matches = sorted(matches, key=operator.itemgetter('version'), reverse=True)

        if list_versions:
            for match in matches:
                click.echo(f"{match['version']}")
            return

        if run_version is "latest":
            match = matches[0]
            click.echo(f"{match['version']}: {match['exec_path']}")
            click.echo(click.get_current_context().args)


def glob_and_match(exec_templates):

    app_matches = []

    for exec_template in exec_templates:

        if "[" in exec_template and "]" in exec_template:
            version_regex = re.compile(r".*\[(?P<version>.*)\].*")
            match = version_regex.match(exec_template)
            ver_template = match.group('version')
            exec_template = exec_template.replace("[", "").replace("]", "")
            # print(exec_template)
        else:
            print("Error: must capture the version string in the template with brackets!")

        token_regex = re.compile(r"\{([a-z]*)\}")
        token_matches = token_regex.findall(exec_template)
        tokens = list(set(token_matches))

        glob_pattern = _format(
            exec_template, dict((key, "*") for key in tokens)
        )
        # print(glob_pattern)

        matching_paths = glob.glob(glob_pattern)
        # print(matching_paths)
        # ['/Applications/Nuke11.1v3/Nuke11.1v3.app/Contents/MacOS/Nuke11.1v3', '/Applications/Nuke12.2v1.Beta3/Nuke12.2v1.Beta3.app/Contents/MacOS/Nuke12.2', '/Applications/Nuke12.2v1.Beta3/Nuke12.2v1.Beta3.app/Contents/MacOS/NukeConfig.cmake']

        exec_regex_pattern = _format(
            exec_template,
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


if __name__ == "__main__":
    main()
