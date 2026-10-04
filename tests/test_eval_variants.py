"""The catalog variants for testing the query-writing rules one at a time."""

import pytest

from evals.text_to_sql import variants

OLD = (
    "# Tables\n\nintro\n\n"
    + variants.TRANSACTIONS
    + "transaction_id, amount\n\n"
    + variants.FX_OLD
    + "\n## customers\nname\n"
)


def test_the_control_is_the_catalog_untouched():
    assert variants.variants(OLD)["old"] == OLD


def test_each_rule_alone_adds_only_that_rule():
    made = variants.variants(OLD)
    assert "strftime" in made["A_dates"] and "ILIKE" not in made["A_dates"]
    assert "ILIKE" in made["B_names"] and "strftime" not in made["B_names"]
    assert "exchange-rate question" in made["C_fx"] and "strftime" not in made["C_fx"]
    assert "ILIKE" not in made["C_fx"] and "exchange-rate question" not in made["A_dates"]


def test_all_the_rules_together_have_all_three():
    text = variants.variants(OLD)["ABC"]
    assert "strftime" in text and "ILIKE" in text and "exchange-rate question" in text
    assert text.count("## Writing the query") == 1


def test_the_rules_land_before_the_tables_and_nothing_else_moves():
    text = variants.variants(OLD)["A_dates"]
    assert text.index("## Writing the query") < text.index(variants.TRANSACTIONS)
    assert (
        text.replace(variants.DATES, "").replace("## Writing the query (PostgreSQL)\n\n\n", "")
        == OLD
    )


def test_a_catalog_that_already_has_the_rules_is_refused():
    with pytest.raises(ValueError, match="no rules yet"):
        variants.variants(variants.variants(OLD)["ABC"])


def test_a_catalog_that_is_not_the_old_one_is_refused():
    with pytest.raises(ValueError, match="exactly once"):
        variants.variants("# some other file\n")


def test_the_command_writes_the_files_and_prints_their_fingerprints(tmp_path, capsys):
    source = tmp_path / "catalog.md"
    source.write_text(OLD)
    assert variants.main([str(source), str(tmp_path / "out")]) == 0
    printed = capsys.readouterr().out
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "ABC.md", "A_dates.md", "B_names.md", "C_fx.md", "old.md",
    ]  # fmt: skip
    assert printed.count("prompt ") == 5
    assert variants.prompt_version(OLD) in printed
    source.write_text("nothing like it")
    assert variants.main([str(source), str(tmp_path / "out2")]) == 2
