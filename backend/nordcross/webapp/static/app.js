const activeTabInput = document.getElementById("active-tab-input");

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(`tab-${button.dataset.tab}`).classList.add("active");
    if (activeTabInput) activeTabInput.value = button.dataset.tab;
    if (button.dataset.tab === "graphs") {
      renderGraphs();
    }
  });
});

const CATEGORY_COLORS = {
  MEN: "#1f5fa8",
  WOMEN: "#c0392b",
  U20_MEN: "#2e8b57",
  U20_WOMEN: "#8e44ad",
};

let graphsRendered = false;

function renderGraphs() {
  if (graphsRendered) {
    Plotly.Plots.resize("chart-left");
    Plotly.Plots.resize("chart-right");
    return;
  }
  graphsRendered = true;

  const data = JSON.parse(document.getElementById("graph-data").textContent);
  const placingsMode = JSON.parse(document.getElementById("placings-mode").textContent);
  const placingsAxisTitle = placingsMode === "last_to_first" ? "Placing (from last)" : "Placing (from first)";

  const leftTraces = data.left.map((series) => {
    const hoverText = series.places.map((place) => {
      const points = series.tooltips[String(place)] || [];
      return points.map((p) => `${p.year} ${p.country} ${p.event_code} ${p.points}pts`).join("<br>");
    });
    return {
      x: series.places,
      y: series.avg_points,
      text: hoverText,
      hovertemplate: "Place %{x}: %{y:.0f} avg pts<br>%{text}<extra></extra>",
      name: series.category_name,
      mode: "lines+markers",
      line: { color: CATEGORY_COLORS[series.category_code] || "#333" },
    };
  });

  Plotly.newPlot("chart-left", leftTraces, {
    margin: { t: 10, r: 10, b: 45, l: 50 },
    xaxis: { title: placingsAxisTitle },
    yaxis: { title: "Average points" },
    legend: { orientation: "h", y: -0.2 },
  }, { responsive: true });

  const rightTraces = data.right.map((series) => ({
    x: series.points,
    y: series.cumulative_pct,
    name: series.category_name,
    mode: "lines",
    line: { shape: "hv", color: CATEGORY_COLORS[series.category_code] || "#333" },
  }));

  Plotly.newPlot("chart-right", rightTraces, {
    margin: { t: 10, r: 10, b: 45, l: 50 },
    xaxis: { title: "Points" },
    yaxis: { title: "Cumulative % of runners", range: [0, 100] },
    legend: { orientation: "h", y: -0.2 },
  }, { responsive: true });
}

// A page load can land directly on the Graphs tab (filters were just
// applied while it was active) -- that skips the click handler above, so
// render explicitly whenever it's already the active panel on load.
if (document.getElementById("tab-graphs")?.classList.contains("active")) {
  renderGraphs();
}
