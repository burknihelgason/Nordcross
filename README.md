# NORDCROSS

Design document for a web/db app for athletic result crunching

## Intro

Every year in November, the Nordic cross country championships are held in NOR/SWE/DEN/FIN/ISL. There are four categories: Men/Women/U20 men/U20 women.
Team selection is tricky because cross country capabilities are not quantifiable in the same way as those on track and road.

## Purpose

To develop a data platform and app to make informed, data-driven decision into team selection for each year's Nordic cross country championships.
This should be based on the capabilities of athletes on track/road and contrasted with the capabilities of participants in years past in the Nordic XC.

## Technical description

I wish to design an app with the following capabilities:
The storage can either be SQL or some sort of file-based system, this will not make for a huge amount of data. Open to discussion and suggestion.

### BACK END

1. Consume results from multiple years of Nordic cross country championships, store in DB or other possibility.
2. Identify as many athletes as possible from the results. Look these up from world athletics and/or other sources and store their track/road PBs and progression by date/year. Register world athletic points with each result.
3. Match the progression data to the Nordic data in time. Identify the best result (in points) of each athlete achieved *before* each result at the Nordics.

### FRONT END

4. Create a web page with the following areas/tabs:

**a: Top banner:** Filtering capabilities. Select 1-4 race categories, 1-5 of the available countries and as many of the available years as requested.

**b: Tab 1: Raw data.** Display results in grids for the races selected in the top banner.

**c: Tab 2: Graphs.** Split into left/right sub-panels.

Left: Display a line graph for each category selected:
- x-axis: Placing in the race (normally 1-25)
- y-axis: The average number of points for the best result of the runner in the place in question calculated over the years selected
- tool tip: The underlying points for each average, showing the following format:
  ```
  2021 SWE 1500m 987pts
  2022 FIN 3000m 1040pts
  2023 NOR 5000m 987pts
  etc.
  ```

Right: Display a line graph for each category selected:
- x-axis: Point, ascending
- y-axis: Cumulative percentage of runners having their best PBs equal or less to the corresponding x-value.

**d: Tab 3. Analytics.** Consider the PBs needed to achieve:
- B-class: Second-to-last place
- A-class: Better than the bottom 10% of runners

Display 3 tables containing the following:
- Table 1, two columns, A and B class. Lines for each category. Content: The points needed to achieve A and B class for each category.
- Table 2, A-class: The results corresponding to each point average in distance events from 800 to the marathon, one column for each category.
- Table 2, B-class: The results corresponding to each point average in distance events from 800 to the marathon, one column for each category.

Implementation steps should be identical to the feature enumeration above, performed and tested one by one.

## Implementation notes

This section tracks how the implementation has evolved past the original spec above, as decisions were made along the way.

- **Storage:** SQL Server, via SQLAlchemy models in `backend/nordcross/db/`.
- **Athlete identification/progression (steps 1-3):** done. Results scraped from multiple national/Nordic result sites; athletes matched and deduplicated across sources; track/road progression pulled from World Athletics (and, where WA search isn't viable, Tilastopaja, friidrottsstatistik.se, and minfriidrettsstatistikk.info via manual profile resolution); WA points computed from the official 2017 scoring tables; each Nordic result matched to the athlete's best points *before* that race's date.
- **Front end (step 4):** a Flask app in `backend/nordcross/webapp/`, built incrementally exactly per the a/b/c/d breakdown above, each tested in-browser before moving to the next:
  - Filter banner state lives in the URL query string (bookmarkable), including which tab is active, so reapplying filters doesn't reset your view.
  - Tab 2's graphs are rendered with Plotly.js; the left panel's hover tooltip matches the spec's example format exactly.
  - A "Placings" toggle (First to last / Last to first) lets the left-panel graph's x-axis run from either end of the field, re-indexed against each individual race's own real finisher count -- this avoids misaligning seasons with different field sizes when looking at the back of the pack.
  - Tab 3's A-class/B-class definitions evolved from the spec's fixed rules (2nd-to-last / bottom 10%) into a single configurable concept: "N places from the top or bottom of the field," independently dialed in per class via banner controls (default: A = 5 from bottom, B = 2 from bottom). Both are computed per race and averaged across the selected years, not pooled across years into one ranked list -- pooling turned "2nd-to-last" into whichever single year happened to have the worst-resolved back-of-pack athlete, an artifact of data coverage rather than a real signal.
  - Equivalent-time tables use a new inverse of the points scoring lookup (`time_for_points` in `nordcross/scoring.py`).
