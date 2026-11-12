
import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.etree import ElementTree as ET

BASE = "https://www.graduateinstitute.ch"

NEWS_URL = (
    BASE + "/research-centres/global-governance-centre/news"
)
EVENTS_URL = (
    BASE + "/centres/global-governance-centre/events"
)
PUBLICATIONS_URL = (
    BASE + "/research-centres/global-governance-centre/publications"
)

OUTPUT = Path("feed.xml")
MIN_PUBLICATION_YEAR = 2026

session = requests.Session()
session.headers.update({
    "User-Agent": "GGC-Content-Feed/1.0"
})


def fetch(url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_text(element, selector):
    found = element.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


def get_link(card):
    link = card.find_parent("a", href=True)
    if not link:
        link = card.select_one("a[href]")

    if not link:
        return None

    url = urljoin(BASE, link["href"])
    if urlparse(url).netloc != urlparse(BASE).netloc:
        return None
    return url


def make_entry(title, url, description, category,
               event_date=None):
    return {
        "title": title,
        "url": url,
        "description": description,
        "category": category,
        "event_date": event_date
    }


def get_news():
    print("Collecting GGC news...")
    soup = fetch(NEWS_URL)
    items = []

    cards = soup.select(
        ".iheid--entity--node--type-news"
    )

    for card in cards:
        title = get_text(card, ".iheid--field--name-title")
        url = get_link(card)

        if not title or not url:
            continue

        try:
            article = fetch(url)

            intro = get_text(
                article,
                ".iheid--field--name-body"
            )

            items.append(make_entry(
                title, url, intro, "News"
            ))
            time.sleep(0.2)

        except requests.RequestException as error:
            print(f"News error: {error}")

    print(f"Found {len(items)} news items")
    return items


def get_events():
    print("Collecting GGC events...")
    soup = fetch(EVENTS_URL)
    items = []

    cards = soup.select(
        ".iheid--entity--node--type-event"
        ".iheid--entity--node--view-mode-small-card"
    )

    for card in cards:
        title = get_text(card, ".iheid--field--name-title")
        url = get_link(card)

        if not title or not url:
            continue

        event_type = get_text(
            card, ".iheid--field--name-field-top-header"
        )
        speakers = get_text(
            card, ".iheid--field--name-field-speakers"
        )
        date = get_text(
            card, ".iheid--field--name-visual-date"
        )
        event_format = get_text(
            card, ".iheid--field--name-field-event-format"
        )

        time_element = card.select_one(
            ".iheid--field--name-field-start-end-date time"
        )

        event_date = (
            time_element.get("datetime")
            if time_element else None
        )
        time_label = (
            time_element.get_text(" ", strip=True)
            if time_element else ""
        )

        details = [
            f"Date: {date}" if date else "",
            f"Time: {time_label}" if time_label else "",
            f"Type: {event_type}" if event_type else "",
            f"Speakers: {speakers}" if speakers else "",
            f"Format: {event_format}" if event_format else ""
        ]

        description = title + "\n\n" + " | ".join(
            part for part in details if part
        )

        items.append(make_entry(
            title, url, description,
            "Event", event_date
        ))

    print(f"Found {len(items)} events")
    return items


def get_publications():
    print("Collecting GGC publications...")
    soup = fetch(PUBLICATIONS_URL)
    items = []

    # Publication listing cards on the Institute website.
    cards = soup.select(
        ".iheid--entity--node--type-publication, "
        ".iheid--entity--node--type-publications"
    )

    for card in cards:
        title = get_text(card, ".iheid--field--name-title")
        url = get_link(card)

        if not title or not url:
            continue

        # Look for an explicitly displayed publication year.
        year_text = get_text(
            card,
            ".iheid--field--name-field-publication-year"
        )

        if not year_text:
            year_text = get_text(
                card,
                ".iheid--field--name-field-year"
            )

        if not year_text:
            # Fallback to a year at the end of the card.
            card_text = card.get_text(" ", strip=True)
            match = re.search(
                r"\b(20\d{2})\s*$", card_text
            )
            year_text = match.group(1) if match else ""

        match = re.search(r"\b(20\d{2})\b", year_text)
        if not match:
            continue

        year = int(match.group(1))

        if year < MIN_PUBLICATION_YEAR:
            continue

        authors = get_text(
            card, ".iheid--field--name-field-authors"
        )

        pub_type = get_text(
            card, ".iheid--field--name-field-type"
        )

        details = [
            title,
            f"Authors: {authors}" if authors else "",
            f"Type: {pub_type}" if pub_type else "",
            f"Publication year: {year}"
        ]

        description = "\n\n".join(
            part for part in details if part
        )

        items.append(make_entry(
            title, url, description, "Publication"
        ))

    print(f"Found {len(items)} publications from 2026 onward")
    return items


def get_existing_dates():
    dates = {}

    if not OUTPUT.exists():
        return dates

    try:
        tree = ET.parse(OUTPUT)

        for item in tree.findall("./channel/item"):
            guid = item.findtext("guid")
            pub_date = item.findtext("pubDate")

            if guid and pub_date:
                dates[guid] = pub_date

    except ET.ParseError:
        print("Existing feed could not be parsed")

    return dates


def make_feed(items):
    existing_dates = get_existing_dates()
    first_seen = format_datetime(
        datetime.now(timezone.utc)
    )

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = (
        "Global Governance Centre - News, Events and Publications"
    )
    ET.SubElement(channel, "link").text = (
        BASE + "/globalgovernance"
    )
    ET.SubElement(channel, "description").text = (
        "News, events and publications from the "
        "Global Governance Centre at the Geneva Graduate Institute"
    )
    ET.SubElement(channel, "language").text = "en"

    seen = set()

    for entry in items:
        if entry["url"] in seen:
            continue

        seen.add(entry["url"])

        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = entry["title"]
        ET.SubElement(item, "link").text = entry["url"]

        ET.SubElement(
            item, "guid", isPermaLink="true"
        ).text = entry["url"]

        description = entry["description"].strip()
        description += (
            "\n\n" if description else ""
        ) + entry["url"]

        ET.SubElement(item, "description").text = description

        ET.SubElement(item, "category").text = (
            entry["category"]
        )

        ET.SubElement(item, "pubDate").text = (
            existing_dates.get(entry["url"], first_seen)
        )

        if entry["event_date"]:
            try:
                dt = datetime.fromisoformat(
                    entry["event_date"].replace("Z", "+00:00")
                )
                ET.SubElement(item, "eventStart").text = (
                    dt.isoformat()
                )
            except ValueError:
                pass

    ET.ElementTree(rss).write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print(f"Created {OUTPUT} with {len(seen)} items")


if __name__ == "__main__":
    news = get_news()
    events = get_events()
    publications = get_publications()

    all_items = news + events + publications

    if not all_items:
        raise RuntimeError(
            "No content found. Check the page selectors."
        )

    make_feed(all_items)
