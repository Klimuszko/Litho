from app.scad.parser import ScadParser


def by_name(source: str):
    return {item.name: item for item in ScadParser().parse(source).parameters}


def test_parses_numeric_ranges_sections_and_types():
    parsed = by_name('''
/* [Main] */
x = 5; // [1:1:10]
ratio = 1.5; // [0.5:0.1:3]
style = "A"; // [A,B,C]
enabled = true;
title = "Example";
''')
    assert parsed["x"].type == "integer"
    assert (parsed["x"].min, parsed["x"].step, parsed["x"].max) == (1, 1, 10)
    assert parsed["ratio"].type == "float"
    assert parsed["style"].type == "enum" and parsed["style"].options == ["A", "B", "C"]
    assert parsed["enabled"].type == "boolean"
    assert parsed["title"].type == "string"
    assert {item.section for item in parsed.values()} == {"Main"}


def test_litho_tags_hidden_advanced_and_metadata():
    parsed = by_name('''
/* [Grip & holes] */
// Used by the customer
finger_hole = 22; // [16:1:30] @unit:mm @label:"Finger hole" @description:"Opening diameter" @order:4
internal_debug = false; // @hidden
helix_angle = 25; // [10:1:45] @advanced @group:"Advanced geometry"
''')
    finger = parsed["finger_hole"]
    assert finger.label == "Finger hole"
    assert finger.description == "Opening diameter"
    assert finger.unit == "mm" and finger.order == 4
    assert parsed["internal_debug"].hidden is True
    assert parsed["helix_angle"].advanced is True
    assert parsed["helix_angle"].section == "Advanced geometry"


def test_malformed_comments_are_reported_without_breaking_valid_parameters():
    result = ScadParser().parse("x = 5; // [one:two]\ny = 2; // [1:1:4]")
    assert [item.name for item in result.parameters] == ["x", "y"]
    assert result.warnings


def test_ignores_expressions_because_parser_is_not_an_interpreter():
    result = ScadParser().parse("derived = width * 2;\nwidth = 10; // [1:1:20]")
    assert [item.name for item in result.parameters] == ["width"]
