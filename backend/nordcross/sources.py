import datetime

from nordcross.scrapers import eqtiming, racetimer, rosterathletics, timataka, tulospalvelu

# Race dates as given by each source (timataka/tulospalvelu event pages,
# rosterathletics schedule, sportsidioten article) except 2021, which
# racetimer.se's pages don't state -- confirmed instead via web search
# (Swedish federation/club coverage of the 7 Nov 2021 event at Lida, Tullinge).
SOURCES = {
    2018: {
        "name": "Nordic Cross Country Championships 2018",
        "url": "https://timataka.net/nccc2018/",
        "scraper": timataka.scrape,
        "date": datetime.date(2018, 11, 10),
    },
    2019: {
        "name": "Nordic Cross Country Championships 2019",
        "url": "https://online4.tulospalvelu.fi/tulokset-new/en/2019_nordic/results/",
        "scraper": tulospalvelu.scrape,
        "date": datetime.date(2019, 11, 10),
    },
    2021: {
        "name": "Nordic Cross Country Championships 2021",
        "url": "https://www.racetimer.se/en/race/show/5012?layout=marathon",
        "scraper": racetimer.scrape,
        "date": datetime.date(2021, 11, 7),
    },
    2022: {
        "name": "Nordic Cross Country Championships 2022",
        "url": "https://www.sportsidioten.no/resultater/resultater-nordisk-mesterskap-terrenglop-2022/",
        "scraper": eqtiming.scrape,
        "date": datetime.date(2022, 11, 6),
    },
    2023: {
        "name": "Nordic Cross Country Championships 2023",
        "url": "https://timataka.net/nccc2023/",
        "scraper": timataka.scrape,
        "date": datetime.date(2023, 11, 5),
    },
    2024: {
        "name": "Nordic Cross Country Championships 2024",
        "url": "https://online.tulospalvelu.fi/tulokset-new/en/2024_nccc/",
        "scraper": tulospalvelu.scrape,
        "date": datetime.date(2024, 11, 10),
    },
    2025: {
        "name": "Nordic Cross Country Championships 2025",
        "url": "https://meets.rosterathletics.com/public/competitions/details/schedule?id=27737",
        "scraper": rosterathletics.scrape,
        "date": datetime.date(2025, 11, 9),
    },
}
