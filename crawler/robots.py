from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests


USER_AGENT = "AinulonBot/0.1 (+https://ainulon.com/bot)"
TIMEOUT = 10


def can_crawl(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )

        if response.status_code >= 400:
            return True

        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)

    except requests.RequestException:
        # Se robots.txt estiver indisponível, não quebramos o crawler.
        return True