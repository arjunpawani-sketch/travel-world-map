import geopandas as gpd
from matplotlib.figure import Figure
from shapely.geometry import box

from src.poster import (
    get_visited_entity_ids,
    render_world_map,
    split_visited_unvisited,
)
from src.validation import build_validation_report


class FakeMappedEntry:
    def __init__(self, entity_ids):
        self.entity_ids = entity_ids


def test_mapped_geometry_retrieval_single_entity(gdf, matcher):
    """A plain single-country match retrieves exactly that entity's geometry."""
    result = matcher.match("Oman")
    assert result.status == "matched"
    assert len(result.entity_ids) == 1
    geometry = gdf.loc[result.entity_ids[0], "geometry"]
    assert geometry is not None
    assert not geometry.is_empty


def test_composite_entity_geometry_covers_all_home_parts(gdf, matcher):
    """United Kingdom composite must include England, Scotland, Wales and
    N. Ireland -- the full mapped entity, not just one constituent part."""
    result = matcher.match("United Kingdom")
    assert result.status == "matched"
    assert result.match_type == "composite"
    assert len(result.entity_ids) == 4

    names = set(gdf.loc[result.entity_ids, "NAME"])
    assert names == {"England", "Scotland", "Wales", "N. Ireland"}

    # Bounds should span from southern England up through northern Scotland.
    geoms = gdf.loc[result.entity_ids, "geometry"]
    combined_bounds = geoms.total_bounds  # minx, miny, maxx, maxy
    assert combined_bounds[1] < 51.5  # south coast of England
    assert combined_bounds[3] > 58.0  # northern Scotland


def test_composite_entity_geometry_antigua_barbuda_has_both_islands(gdf, matcher):
    result = matcher.match("Antigua and Barbuda")
    assert result.status == "matched"
    names = set(gdf.loc[result.entity_ids, "NAME"])
    assert names == {"Antigua", "Barbuda"}


def test_visited_unvisited_classification():
    fake_gdf = gpd.GeoDataFrame(
        {"NAME": ["A", "B", "C"]},
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)],
        crs="EPSG:4326",
    )
    mapped = [FakeMappedEntry([0]), FakeMappedEntry([2])]
    visited_ids = get_visited_entity_ids(mapped)
    assert visited_ids == {0, 2}

    visited_gdf, unvisited_gdf = split_visited_unvisited(fake_gdf, visited_ids)
    assert set(visited_gdf["NAME"]) == {"A", "C"}
    assert set(unvisited_gdf["NAME"]) == {"B"}


def test_renderer_returns_valid_figure(gdf, default_workbook_path, matcher):
    report = build_validation_report(default_workbook_path, gdf, matcher)
    fig = render_world_map(gdf, report.mapped, width=6, height=3, dpi=72, preview=True)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 1


def test_rendering_does_not_mutate_source_geographic_data(gdf, default_workbook_path, matcher):
    original_columns = list(gdf.columns)
    original_len = len(gdf)
    original_crs = gdf.crs
    original_wkb = gdf.geometry.apply(lambda g: g.wkb).tolist()

    report = build_validation_report(default_workbook_path, gdf, matcher)
    render_world_map(gdf, report.mapped, width=6, height=3, dpi=72, preview=True)

    assert list(gdf.columns) == original_columns
    assert len(gdf) == original_len
    assert gdf.crs == original_crs
    assert gdf.geometry.apply(lambda g: g.wkb).tolist() == original_wkb
