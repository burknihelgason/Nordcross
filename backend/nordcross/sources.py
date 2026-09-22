from nordcross.scrapers import timataka

SOURCES = {
    2018: {
        "name": "Nordic Cross Country Championships 2018",
        "url": "https://timataka.net/nccc2018/",
        "scraper": timataka.scrape,
    },
    2023: {
        "name": "Nordic Cross Country Championships 2023",
        "url": "https://timataka.net/nccc2023/",
        "scraper": timataka.scrape,
    },
}
