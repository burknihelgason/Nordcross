from nordcross.scrapers import racetimer, timataka, tulospalvelu

SOURCES = {
    2018: {
        "name": "Nordic Cross Country Championships 2018",
        "url": "https://timataka.net/nccc2018/",
        "scraper": timataka.scrape,
    },
    2019: {
        "name": "Nordic Cross Country Championships 2019",
        "url": "https://online4.tulospalvelu.fi/tulokset-new/en/2019_nordic/results/",
        "scraper": tulospalvelu.scrape,
    },
    2021: {
        "name": "Nordic Cross Country Championships 2021",
        "url": "https://www.racetimer.se/en/race/show/5012?layout=marathon",
        "scraper": racetimer.scrape,
    },
    2023: {
        "name": "Nordic Cross Country Championships 2023",
        "url": "https://timataka.net/nccc2023/",
        "scraper": timataka.scrape,
    },
    2024: {
        "name": "Nordic Cross Country Championships 2024",
        "url": "https://online.tulospalvelu.fi/tulokset-new/en/2024_nccc/",
        "scraper": tulospalvelu.scrape,
    },
}
