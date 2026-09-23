from dataclasses import asdict

from flask import Blueprint, render_template, request

from nordcross.db.session import get_session
from nordcross.webapp.analytics import get_class_points, get_event_time_table
from nordcross.webapp.filters import get_available_filters, parse_active_tab, parse_selected_filters
from nordcross.webapp.graphs import get_left_panel_data, get_right_panel_data
from nordcross.webapp.raw_data import get_raw_result_grids

bp = Blueprint("views", __name__)


@bp.route("/")
def index():
    session = get_session()
    try:
        available = get_available_filters(session)
        selected = parse_selected_filters(request.args, available)
        active_tab = parse_active_tab(request.args)
        race_grids = get_raw_result_grids(session, selected)
        left_panel = get_left_panel_data(session, selected, available.categories)
        right_panel = get_right_panel_data(session, selected, available.categories)
        class_points = get_class_points(session, selected, available.categories)
        b_class_table = get_event_time_table(class_points, "b_class_points")
        a_class_table = get_event_time_table(class_points, "a_class_points")
    finally:
        session.close()

    # json.dumps stringifies dict keys automatically, so asdict()'s
    # int-keyed `tooltips` dict serializes to {"5": [...]} as-is.
    graph_data = {
        "left": [asdict(s) for s in left_panel],
        "right": [asdict(s) for s in right_panel],
    }

    return render_template(
        "index.html",
        available=available,
        selected=selected,
        active_tab=active_tab,
        race_grids=race_grids,
        graph_data=graph_data,
        class_points=class_points,
        a_class_table=a_class_table,
        b_class_table=b_class_table,
    )
