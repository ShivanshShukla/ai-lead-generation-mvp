import re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "Mozilla/5.0"
CANDIDATE_PATHS = [
    "",
    "contact",
    "contact-us",
    "about",
    "about-us",
    "team",
    "careers",
]

FAKE_EMAILS = {
    "example@example.com",
    "test@test.com",
    "yourname@example.com",
    "name@example.com",
}
FAKE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
}

robots_cache = {}


def normalize_url(url: str) -> str:
    cleaned_url = (url or "").strip()

    if not cleaned_url:
        return ""

    if cleaned_url.startswith("//"):
        cleaned_url = f"https:{cleaned_url}"

    parsed_url = urlparse(cleaned_url)

    if not parsed_url.scheme:
        cleaned_url = f"https://{cleaned_url}"

    return cleaned_url.rstrip("/")


def extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []

    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    matches = re.findall(email_pattern, text)
    emails = []
    seen = set()

    for match in matches:
        email = match.strip(".,;:()[]{}<>\"'").lower()
        domain = email.split("@")[-1]

        if email in FAKE_EMAILS or domain in FAKE_EMAIL_DOMAINS:
            continue

        if email not in seen:
            seen.add(email)
            emails.append(email)

    return emails


def is_allowed_by_robots(url: str) -> tuple[bool, str | None]:
    parsed_url = urlparse(url)

    if not parsed_url.scheme or not parsed_url.netloc:
        return False, "Invalid website URL"

    robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

    if robots_url not in robots_cache:
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            response = requests.get(
                robots_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )

            if response.status_code >= 400:
                robots_cache[robots_url] = None
            else:
                parser.parse(response.text.splitlines())
                robots_cache[robots_url] = parser
        except requests.RequestException:
            robots_cache[robots_url] = None

    parser = robots_cache[robots_url]

    if parser is None:
        return True, None

    if not parser.can_fetch(USER_AGENT, url):
        return False, "Robots.txt disallows scraping this page"

    return True, None


def fetch_page_html(url: str) -> tuple[str, str | None]:
    allowed, robots_error = is_allowed_by_robots(url)

    if not allowed:
        return "", robots_error

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.text, None
    except requests.RequestException as exc:
        return "", str(exc)


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return soup.get_text(" ", strip=True)


def fetch_page_text(url: str) -> str:
    html, error = fetch_page_html(url)

    if error or not html:
        return ""

    return extract_visible_text(html)


def build_candidate_urls(base_url: str) -> list[str]:
    normalized_url = normalize_url(base_url)
    parsed_url = urlparse(normalized_url)

    if not parsed_url.scheme or not parsed_url.netloc:
        return []

    root_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"

    return [urljoin(root_url, path) for path in CANDIDATE_PATHS]


def find_emails_from_website(website: str) -> dict:
    normalized_website = normalize_url(website)

    if not normalized_website:
        return {
            "emails": [],
            "pages_checked": [],
            "error": "Website is missing"
        }

    candidate_urls = build_candidate_urls(normalized_website)

    if not candidate_urls:
        return {
            "emails": [],
            "pages_checked": [],
            "error": "Invalid website URL"
        }

    found_emails = []
    seen_emails = set()
    pages_checked = []
    last_error = None
    successful_fetches = 0

    for candidate_url in candidate_urls:
        print(f"Checking page for public emails: {candidate_url}")
        pages_checked.append(candidate_url)

        html, error = fetch_page_html(candidate_url)

        if error:
            last_error = error
            continue

        if not html:
            continue

        successful_fetches += 1
        visible_text = extract_visible_text(html)
        page_emails = extract_emails_from_text(f"{visible_text} {html}")

        for email in page_emails:
            if email not in seen_emails:
                seen_emails.add(email)
                found_emails.append(email)

        if found_emails:
            break

    error = None

    if not found_emails and successful_fetches == 0 and last_error:
        error = last_error

    return {
        "emails": found_emails,
        "pages_checked": pages_checked,
        "error": error
    }
