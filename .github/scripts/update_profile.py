import html
import json
import os
import re
from itertools import count
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ACTIVITY_LIMIT = 3
PAGE_SIZE = 100
SNAKE_LIGHT = Path("assets/contribution-snake.svg")
SNAKE_DARK = Path("assets/contribution-snake-dark.svg")
ACTIVITY_LINKS = "[Recent repositories][repos] · [Public pull requests][public-prs]"


def fetch_github(path, **query):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-readme"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/{path}?{urlencode(query)}"
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def recent_repositories(owner, profile_repo):
    entries = []
    for page in count(1):
        repositories = fetch_github(
            f"users/{owner}/repos",
            type="owner",
            sort="pushed",
            direction="desc",
            per_page=PAGE_SIZE,
            page=page,
        )
        for repo in repositories:
            if (
                repo["fork"]
                or repo["archived"]
                or repo["private"]
                or repo["full_name"].casefold() == profile_repo.casefold()
                or not repo["pushed_at"]
            ):
                continue
            entries.append((repo["pushed_at"], repo["name"], repo["html_url"]))
            if len(entries) == ACTIVITY_LIMIT:
                return entries
        if len(repositories) < PAGE_SIZE:
            return entries


def recent_pull_requests(owner):
    results = fetch_github(
        "search/issues",
        q=f"is:pr is:public author:{owner}",
        sort="created",
        order="desc",
        per_page=ACTIVITY_LIMIT,
    )
    if results["incomplete_results"]:
        raise RuntimeError("GitHub returned incomplete pull request search results")

    entries = []
    for pull in results["items"]:
        repo = pull["repository_url"].rsplit("/", 1)[-1]
        label = f"{repo} #{pull['number']} · {pull['title']}"
        entries.append((pull["created_at"], label, pull["html_url"]))
    return entries


def activity_markdown(entries):
    lines = []
    for timestamp, label, url in sorted(entries, reverse=True)[:ACTIVITY_LIMIT]:
        label = html.escape(" ".join(label.split()), quote=False)
        label = re.sub(r"([\\`*_\[\]~])", r"\\\1", label)
        lines.append(f"- [{label}]({url}) · `{timestamp[:10]}`")
    return "\n".join([*lines, "", ACTIVITY_LINKS]) if lines else ACTIVITY_LINKS


def replace_block(markdown, name, content):
    start = f"<!-- profile-{name}:start -->"
    end = f"<!-- profile-{name}:end -->"
    if markdown.count(start) != 1 or markdown.count(end) != 1:
        raise ValueError(f"Expected one marker pair for {name}")
    before, remainder = markdown.split(start, 1)
    _, found, after = remainder.partition(end)
    if not found:
        raise ValueError(f"Markers for {name} are out of order")
    return f"{before}{start}\n{content}\n{end}{after}"


def main():
    profile_repo = os.environ["GITHUB_REPOSITORY"]
    owner = profile_repo.split("/")[0]
    entries = recent_repositories(owner, profile_repo) + recent_pull_requests(owner)
    readme = Path("README.md")
    original = readme.read_text(encoding="utf-8")
    updated = replace_block(original, "activity", activity_markdown(entries))

    if SNAKE_LIGHT.is_file() and SNAKE_DARK.is_file():
        snake = (
            "<picture>\n"
            f'  <source media="(prefers-color-scheme: dark)" srcset="{SNAKE_DARK.as_posix()}" />\n'
            f'  <img alt="Animated GitHub contribution calendar" src="{SNAKE_LIGHT.as_posix()}" />\n'
            "</picture>"
        )
        updated = replace_block(updated, "snake", snake)

    if updated != original:
        readme.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
