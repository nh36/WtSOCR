import csv
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEM_PATH = ROOT / "scripts" / "postprocess_entry_map.py"
PEM_SPEC = importlib.util.spec_from_file_location("postprocess_entry_map", PEM_PATH)
if PEM_SPEC is None or PEM_SPEC.loader is None:
    raise ImportError(f"Could not load postprocess_entry_map module from {PEM_PATH}")
pem = importlib.util.module_from_spec(PEM_SPEC)
sys.modules[PEM_SPEC.name] = pem
PEM_SPEC.loader.exec_module(pem)


class PostprocessRegressionTests(unittest.TestCase):
    def run_postprocess_fixture(
        self,
        merged_text: str,
        *,
        google_vision: bool = False,
        alternate_merged_text: str | None = None,
        alternate_google_vision: bool = False,
        merge_only: bool = False,
        label: str = "fixture",
    ) -> tuple[dict[str, object], str, list[dict[str, str]]]:
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, ignore_errors=True)
        root = Path(td)
        merged = root / "fixture_merged.txt"
        alternate_merged = root / "fixture_alternate_merged.txt"
        outdir = root / "out"
        merged.write_text(merged_text, encoding="utf-8")
        if alternate_merged_text is not None:
            alternate_merged.write_text(alternate_merged_text, encoding="utf-8")
        outdir.mkdir(parents=True, exist_ok=True)

        result = pem.run_one(
            merged=merged,
            audit=None,
            outdir=outdir,
            label=label,
            trusted_min_freq=2,
            discover_max_edit=2,
            discover_max_rare_freq=3,
            google_vision=google_vision,
            alternate_merged=alternate_merged if alternate_merged_text is not None else None,
            alternate_google_vision=alternate_google_vision,
            merge_only=merge_only,
        )
        corrected = Path(result["corrected_full"]).read_text(encoding="utf-8")
        with Path(result["changes_tsv"]).open(newline="", encoding="utf-8") as f:
            changes = list(csv.DictReader(f, delimiter="\t"))
        return result, corrected, changes

    @staticmethod
    def fixture_with_reviewed_lines(lines_by_page_line: dict[tuple[int, int], str]) -> str:
        max_page = max(page for page, _ in lines_by_page_line)
        pages: list[str] = []
        for page in range(1, max_page + 1):
            page_lines = ["placeholder"]
            for (target_page, line), text in sorted(lines_by_page_line.items()):
                if target_page != page:
                    continue
                while len(page_lines) < line:
                    page_lines.append("filler line")
                page_lines[line - 1] = text
            pages.append("\n".join(page_lines))
        return "\f".join(pages)

    def test_run_one_tolerates_malformed_ocr_bytes(self) -> None:
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, ignore_errors=True)
        root = Path(td)
        merged = root / "fixture_merged.txt"
        alternate_merged = root / "fixture_alternate_merged.txt"
        outdir = root / "out"
        outdir.mkdir(parents=True, exist_ok=True)
        merged.write_bytes("=== page 001 ===\nཀ་ ka ".encode("utf-8") + b"\xff\n")
        alternate_merged.write_bytes(
            "=== page 001 ===\nཀ་ ka ".encode("utf-8") + b"\xfe\n"
        )

        result = pem.run_one(
            merged=merged,
            audit=None,
            outdir=outdir,
            label="fixture",
            trusted_min_freq=2,
            discover_max_edit=2,
            discover_max_rare_freq=3,
            alternate_merged=alternate_merged,
        )

        corrected = Path(result["corrected_full"]).read_text(encoding="utf-8")
        self.assertIn("\ufffd", corrected)

    def test_google_vision_loc_confusables_tibetan_context(self) -> None:
        merged_text = "བྱང་ byaň\nབཟང་ bzań po žes šes rab\n"
        result, corrected, changes = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("byaṅ", corrected)
        self.assertIn("bzaṅ po źes śes rab", corrected)
        self.assertEqual(result["google_vision_rewrites"], 4)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("byaň", "byaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("bzań", "bzaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("žes", "źes", "google_vision_loc_confusable"), reasons)
        self.assertIn(("šes", "śes", "google_vision_loc_confusable"), reasons)

    def test_google_vision_loc_confusables_protects_slavic_bibliography(self) -> None:
        merged_text = "བྱང་ byaň\nŠčerbackoj 1904: Nyāyabindu.\n"
        _, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("byaṅ", corrected)
        self.assertIn("Ščerbackoj", corrected)
        self.assertNotIn("Śčerbackoj", corrected)

    def test_google_vision_loc_confusables_raw_vision_line_without_entry_context(self) -> None:
        merged_text = "Kah thog rig 'dzin Tshe dbaň nor bu'i žabs kyi rnam thar\n"
        result, corrected, changes = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("dbaṅ", corrected)
        self.assertIn("źabs", corrected)
        self.assertEqual(result["google_vision_rewrites"], 2)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("dbaň", "dbaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("žabs", "źabs", "google_vision_loc_confusable"), reasons)

    def test_google_vision_page_markers_are_normalized(self) -> None:
        merged_text = (
            "=== page 001 ===\n"
            "བྱང་ byaň\n"
            "=== page 002 ===\n"
            "གསང་ gsań\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("\f", corrected)
        self.assertIn("byaṅ", corrected)
        self.assertIn("gsaṅ", corrected)
        self.assertEqual(result["google_vision_rewrites"], 2)

    def test_google_vision_nasal_confusables_keep_palatal_nasal_clusters(self) -> None:
        merged_text = "mňam pa sniň po gňis mňon dňul\n"
        result, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("mñam pa sñiṅ po gñis mṅon dṅul", corrected)
        self.assertEqual(result["google_vision_rewrites"], 5)

    def test_alternate_witness_adopts_clean_translit_token(self) -> None:
        merged_text = "ཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "žes")
        self.assertEqual(adoptions[0]["alternate_token"], "źes")
        self.assertEqual(adoptions[0]["reason"], "alternate_witness_strict_translit")
        self.assertEqual(adoptions[0]["alignment_method"], "ordinary_page_alignment")
        self.assertEqual(adoptions[0]["alignment_attribution"], "ordinary_page_alignment")
        self.assertEqual(
            adoptions[0]["resynchronization_attribution"],
            "direct_page_alignment",
        )
        self.assertEqual(adoptions[0]["base_to_alternate_page_delta"], "0")

    def test_alternate_witness_logs_unresolved_unsafe_disagreement(self) -> None:
        merged_text = "ཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཀོང་ kuṅ po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "koṅ")
        self.assertEqual(unresolved[0]["alternate_token"], "kuṅ")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_adopts_google_loc_fricative_upgrade(self) -> None:
        merged_text = "ཞེས་ zes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "zes")
        self.assertEqual(adoptions[0]["alternate_token"], "źes")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_fricative_upgrade",
        )

    def test_alternate_witness_adopts_google_loc_nasal_upgrade(self) -> None:
        merged_text = "ཀོང་ kon po\n"
        alternate_merged_text = "=== page 001 ===\nཀོང་ koň po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "kon")
        self.assertEqual(adoptions[0]["alternate_token"], "koṅ")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_nasal_upgrade",
        )

    def test_alternate_witness_adopts_google_loc_velar_nasal_upgrade(self) -> None:
        merged_text = "ཀོང་ koñ po\n"
        alternate_merged_text = "=== page 001 ===\nཀོང་ koṅ po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "koñ")
        self.assertEqual(adoptions[0]["alternate_token"], "koṅ")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_velar_nasal_upgrade",
        )

    def test_alternate_witness_blocks_google_loc_velar_nasal_upgrade_for_sanskrit_shape(
        self,
    ) -> None:
        merged_text = "གནས་ gañdza\n"
        alternate_merged_text = "=== page 001 ===\nགནས་ gaṅdza\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gañdza", corrected)
        self.assertNotIn("gaṅdza", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "gañdza")
        self.assertEqual(unresolved[0]["alternate_token"], "gaṅdza")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_blocks_bad_dnos_palatal_nasal(self) -> None:
        merged_text = "དངོས་ dnos su gsal por ma ston par\n"
        alternate_merged_text = "=== page 001 ===\nདངོས་ dños su gsal por ma ston par\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("dnos su", corrected)
        self.assertNotIn("dños", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "dnos")
        self.assertEqual(unresolved[0]["alternate_token"], "dños")
        self.assertEqual(
            unresolved[0]["reason"],
            "blocked_alternate_witness_wrong_nasal_dnos",
        )

    def test_alternate_witness_keeps_gna_khri_palatal_nasal_upgrade(self) -> None:
        merged_text = "གཉ་ gNa-khri btsan-po\n"
        alternate_merged_text = "=== page 001 ===\nགཉ་ gÑa-khri btsan-po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gÑa-khri", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "gNa-khri")
        self.assertEqual(adoptions[0]["alternate_token"], "gÑa-khri")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_nasal_upgrade",
        )

    def test_reviewed_wts_9m_dnos_exact_local_normalization(self) -> None:
        pages = ["placeholder\n"] * 67
        pages.append("filler line\nLex. la sogs pa = dnos su gsal por ma ston par\n")
        merged_text = "\f".join(pages)

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("dṅos su", corrected)
        reviewed = [
            row for row in changes if row["reason"] == "reviewed_tibetan_exact_dngos"
        ]
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["page"], "68")
        self.assertEqual(reviewed[0]["line"], "2")
        self.assertEqual(reviewed[0]["from_token"], "dnos")
        self.assertEqual(reviewed[0]["to_token"], "dṅos")
        self.assertEqual(reviewed[0]["tier"], "reviewed_tibetan_exact")
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

    def test_reviewed_wts_9m_dnos_exact_does_not_apply_unreviewed_line(self) -> None:
        pages = ["placeholder\n"] * 67
        pages.append(
            "filler line\n"
            "another line\n"
            "Lex. la sogs pa = dnos su gsal por ma ston par\n"
        )
        merged_text = "\f".join(pages)

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("dnos su", corrected)
        self.assertNotIn("dṅos", corrected)
        self.assertFalse(
            [row for row in changes if row["reason"] == "reviewed_tibetan_exact_dngos"]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_wts_9m_remaining_dnos_rows_are_exactly_gated(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (143, 10): "Lex. chos kyi sogs dnos po'i rigs tshon",
                (190, 77): "sa' dnos gi tshig don gñis ka",
                (381, 57): "drug gi rnam len gyi bya bas dnos su ma zin",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("sogs dṅos po'i", corrected)
        self.assertIn("sa' dṅos gi", corrected)
        self.assertIn("bas dṅos su", corrected)
        self.assertNotIn("dños", corrected)
        reviewed = [
            row for row in changes if row["reason"] == "reviewed_tibetan_exact_dngos"
        ]
        self.assertEqual(len(reviewed), 3)
        self.assertEqual(
            {
                (
                    row["page"],
                    row["line"],
                    row["from_token"],
                    row["to_token"],
                    row["tier"],
                )
                for row in reviewed
            },
            {
                ("143", "10", "dnos", "dṅos", "reviewed_tibetan_exact"),
                ("190", "77", "dnos", "dṅos", "reviewed_tibetan_exact"),
                ("381", "57", "dnos", "dṅos", "reviewed_tibetan_exact"),
            },
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_tibetan_exact_loader_reads_tsv(self) -> None:
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        path = Path(tmpdir) / "reviewed.tsv"
        path.write_text(
            "volume\tpage\tline\ttoken_index\tfrom_token\tto_token\treason\tevidence\treview_note\n"
            "WtS 9-m\t12\t3\t4\tdnos\tdṅos\treviewed_tibetan_exact_dngos\ttest\tfixture\n",
            encoding="utf-8",
        )

        rows = pem.load_reviewed_tibetan_exact_normalizations(path)

        self.assertEqual(
            rows[("wts_9_m", 12, 3, 4, "dnos")],
            ("dṅos", "reviewed_tibetan_exact_dngos"),
        )

    def test_reviewed_wts_8b_final_ng_exact_batch_normalization(self) -> None:
        reviewed_lines = {
            (69, 16): 'die sañ gsen mit dem Wollschopf [usw.]"',
            (109, 71): 'tses dki? ~ te "Myañ Zan-snan war gegen-',
            (150, 30): "(dPeD 185,6); bya de po ni khyim bya'i miñ",
            (186, 65): "gtogs pai miñ).",
            (212, 14): 'sañ Sari dari ~ dari sgum thun "Sari sar, kleine',
            (232, 30): 'schein" (Tär 161,10); ~ dan / sa sho sañ son',
            (269, 53): "Lex. bram zei bu (abw. Ms L bram zei du brtsi bæi miñ).",
            (309, 57): '~ pa "Myañ und dBa\'s hielten eine Rede"',
            (436, 53): 'er, Glanz" (Mvy 3038, Abt. od kyi miñ); gsal',
            (464, 41): 'gen entstehen" (Siddh 17.8); den sañ gi bar',
            (522, 60): 'Lex. lbu bæi miñ "Bez. für Schaum" (Dagy);',
            (526, 92): '"früher waren sich Myañ und dBa\'s ähnlich',
            (553, 75): 'pa dra nas "wenn man [Myañ] mit dBa\'s ver-',
            (553, 76): "gleicht, scheint fiir Myañ die Gunst gerin-",
            (564, 71): "(Rol 77,4,2); bod sgra ... phal cher miñ gi thog",
            (572, 82): 'sañ ni ~i skad tsam mi sgrog par snan "dies',
        }
        merged_text = self.fixture_with_reviewed_lines(reviewed_lines)

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("saṅ gsen", corrected)
        self.assertIn("Myaṅ Zan-snan", corrected)
        self.assertIn("khyim bya'i miṅ", corrected)
        self.assertIn("gtogs pai miṅ).", corrected)
        reviewed = [
            row for row in changes if row["reason"] == "reviewed_tibetan_exact_final_ng"
        ]
        self.assertEqual(len(reviewed), 16)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 16)
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})

    def test_reviewed_wts_8b_final_ng_does_not_apply_unreviewed_line(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (69, 17): 'die sañ gsen mit dem Wollschopf [usw.]"',
                (109, 72): 'tses dki? ~ te "Myañ Zan-snan war gegen-',
                (150, 31): "(dPeD 185,6); bya de po ni khyim bya'i miñ",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("sañ gsen", corrected)
        self.assertIn("Myañ Zan-snan", corrected)
        self.assertIn("khyim bya'i miñ", corrected)
        self.assertFalse(
            [row for row in changes if row["reason"] == "reviewed_tibetan_exact_final_ng"]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_wts_9m_final_ng_exact_batch_normalization(self) -> None:
        reviewed_lines = {
            (57, 3): 'deri sañ chi na zer "Name für Großchina, es',
            (66, 24): 'sgyit phab ste "Myañ Mañ-po-rje Zan-snan',
            (258, 5): 'Bum-thañ verborgen ist" (Padm 353b3); ~',
            (302, 40): 'Lex. ba lañ dkar zal dmar zal khra khra lta bu',
            (351, 22): "dBus-gtsañ, den vier Hörnern, durchwan-",
            (394, 14): 'was falsch gemacht hat" (NBT 205,19); añ',
        }
        merged_text = self.fixture_with_reviewed_lines(reviewed_lines)

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("deri saṅ chi", corrected)
        self.assertIn('sgyit phab ste "Myaṅ Maṅ-po-rje', corrected)
        self.assertIn("Bum-thaṅ verborgen", corrected)
        self.assertIn("ba laṅ dkar", corrected)
        self.assertIn("dBus-gtsaṅ", corrected)
        self.assertIn("NBT 205,19); aṅ", corrected)
        reviewed = [
            row for row in changes if row["reason"] == "reviewed_tibetan_exact_final_ng"
        ]
        self.assertEqual(len(reviewed), 7)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 7)
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})

    def test_reviewed_wts_9m_final_ng_does_not_apply_unreviewed_line(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (57, 4): 'deri sañ chi na zer "Name für Großchina, es',
                (66, 25): 'sgyit phab ste "Myañ Mañ-po-rje Zan-snan',
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("sañ chi", corrected)
        self.assertIn("Myañ Mañ-po-rje", corrected)
        self.assertFalse(
            [row for row in changes if row["reason"] == "reviewed_tibetan_exact_final_ng"]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_wts_9m_exact_local_cleanup_normalization(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (229, 33): 'gibt keinen Handelnden" (AA 3.9a); dnos',
                (351, 41): "gNa-khri btsan-po an bis zu den drei spä-",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("AA 3.9a); dṅos", corrected)
        self.assertIn("gÑa-khri btsan-po", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 2)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("dnos", "dṅos", "reviewed_tibetan_exact_dngos"), reasons)
        self.assertIn(("gNa-khri", "gÑa-khri", "reviewed_tibetan_exact_gna_khri"), reasons)

    def test_reviewed_tibetan_medium_cleanup_batch_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (12, 26): "Lex. ba ku (v.|. kku) la'am dnos su bZag (v..",
                (15, 61): 'dern des Körpers bewegen sich nicht" (VisT',
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("la'am dṅos su bZag", corrected)
        self.assertIn('(ViśT', corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 2)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("dnos", "dṅos", "reviewed_tibetan_exact_dngos"), reasons)
        self.assertIn(("VisT", "ViśT", "reviewed_siglum_exact_visht"), reasons)

    def test_reviewed_sigla_registry_cleanup_examples_wts_8b(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (15, 10): 'als Lehnwort [im Tibetischen] ba dan" (Lis',
                (49, 77): 'dBus-gtsañ mit den vier Hörnern" (Sambh',
                (83, 34): 'boren wurde, hat noch keinen Zahn" (Bu-Sz',
                (124, 23): 'phie, der Mantras und des Geistes" (Lsdz-K',
                (384, 53): 'brechen, Atemnot und Hämorrhoiden" (Ys',
                (388, 68): 'te "Atiśa ging allmählich nach dBus" (Bu-S;',
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("(Liś", corrected)
        self.assertIn("(Śambh", corrected)
        self.assertIn("(Bu-śz", corrected)
        self.assertIn("(Lśdz-K", corrected)
        self.assertIn("(Yś", corrected)
        self.assertIn("(Bu-śz;", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_siglum_exact_registry_canonicalization"
        ]
        self.assertEqual(len(reviewed), 6)
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})
        self.assertEqual(
            {
                (row["from_token"], row["to_token"])
                for row in reviewed
            },
            {
                ("Lis", "Liś"),
                ("Sambh", "Śambh"),
                ("Bu-Sz", "Bu-śz"),
                ("Lsdz-K", "Lśdz-K"),
                ("Ys", "Yś"),
                ("Bu-S", "Bu-śz"),
            },
        )

    def test_reviewed_sigla_registry_cleanup_examples_wts_9m(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (25, 81): 'Untergangs nicht zu unterscheiden" (GS-H',
                (276, 67): 'ist instabil, Jugend vergeht schnell" (Gs-H',
                (316, 27): 'ter gekommen sei, sei er ein Gott" (Bu-$z',
                (340, 22): "(brDa); blun po (TTC); - ni blun po (Lis",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("(Gś-H", corrected)
        self.assertIn("(Bu-śz", corrected)
        self.assertIn("(Liś", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 4)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_siglum_exact_registry_canonicalization"
        ]
        self.assertEqual(len(reviewed), 4)
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})
        self.assertEqual(
            {
                (row["from_token"], row["to_token"])
                for row in reviewed
            },
            {
                ("GS-H", "Gś-H"),
                ("Gs-H", "Gś-H"),
                ("Bu-$z", "Bu-śz"),
                ("Lis", "Liś"),
            },
        )

    def test_reviewed_sigla_registry_cleanup_does_not_apply_unreviewed_context(
        self,
    ) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (15, 11): "plain lexical lis gzi AA_LIS_LY",
                (25, 82): "plain text Bu-Sz GS-H Ys Sambh Lsdz-K Bu-$z",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("plain lexical lis gzi AA_LIS_LY", corrected)
        self.assertIn("plain text Bu-Sz GS-H Ys Sambh Lsdz-K Bu-$z", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_siglum_exact_registry_canonicalization"
            ]
        )

    def test_reviewed_tibetan_initial_i_exact_cleanup_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (5, 4): "x Iha",
                (6, 54): "a b c d e f Idan",
                (7, 37): "a b c d Ita",
                (7, 87): "x Ina",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("x lha", corrected)
        self.assertIn("a b c d e f ldan", corrected)
        self.assertIn("a b c d lta", corrected)
        self.assertIn("x lṅa", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 4)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_initial_i_l_family"
        ]
        self.assertEqual(len(reviewed), 4)
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})

    def test_reviewed_tibetan_initial_i_residual_batch_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (13, 80): "a b c d e f g h Ina",
                (20, 85): "Itar",
                (59, 64): "a b c d Ipags",
                (75, 72): "a b Ius",
                (167, 43): "Ikog",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_1_34",
        )

        self.assertIn("a b c d e f g h lṅa", corrected)
        self.assertIn("ltar", corrected)
        self.assertIn("a b c d lpags", corrected)
        self.assertIn("a b lus", corrected)
        self.assertIn("lkog", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 5)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_initial_i_l_family"
        ]
        self.assertEqual(
            {(row["from_token"], row["to_token"]) for row in reviewed},
            {
                ("Ina", "lṅa"),
                ("Itar", "ltar"),
                ("Ipags", "lpags"),
                ("Ius", "lus"),
                ("Ikog", "lkog"),
            },
        )
        self.assertEqual({row["tier"] for row in reviewed}, {"reviewed_tibetan_exact"})

    def test_reviewed_tibetan_initial_i_exact_does_not_apply_unreviewed_line(
        self,
    ) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (5, 5): "x Iha",
                (6, 55): "a b c d e f Idan",
                (7, 38): "a b c d Ita",
                (7, 88): "x Ina",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("x Iha", corrected)
        self.assertIn("a b c d e f Idan", corrected)
        self.assertIn("a b c d Ita", corrected)
        self.assertIn("x Ina", corrected)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_initial_i_l_family"
            ]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_tibetan_residual_ng_and_google_candidate_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (15, 53): "a b c d e f g dań",
                (232, 44): "a b c d e f kyan run",
                (232, 51): "Ses a b c",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("a b c d e f g daṅ", corrected)
        self.assertIn("a b c d e f kyaṅ ruṅ", corrected)
        self.assertIn("śes a b c", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 4)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("dań", "daṅ", "reviewed_tibetan_exact_residual_ng"), reasons)
        self.assertIn(
            ("kyan", "kyaṅ", "reviewed_tibetan_exact_google_tibetan_candidate"),
            reasons,
        )
        self.assertIn(
            ("run", "ruṅ", "reviewed_tibetan_exact_google_tibetan_candidate"),
            reasons,
        )
        self.assertIn(
            ("Ses", "śes", "reviewed_tibetan_exact_google_tibetan_candidate"),
            reasons,
        )

    def test_reviewed_tibetan_candidate_cleanup_does_not_apply_unreviewed_context(
        self,
    ) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (15, 54): "a b c d e f g dań",
                (232, 45): "a b c d e f kyan run",
                (232, 52): "Ses a b c",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("a b c d e f g dań", corrected)
        self.assertIn("a b c d e f kyan run", corrected)
        self.assertIn("Ses a b c", corrected)
        self.assertFalse(
            [row for row in changes if row["tier"] == "reviewed_tibetan_exact"]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_tibetan_residual_context_cleanup_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (229, 70): "a b c d e f rkani rjes",
                (229, 87): "a b c d e f rkani khal rria",
                (232, 21): "a b c d e zani ziri gi 'bul",
                (233, 69): "a b c d e sriar gi Nlams",
                (285, 67): "gtsani khul nina' ris dan bcas kyi",
                (362, 53): "giun don ses / las rnams mthon Zin gtsari ba",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("a b c d e f rkaṅ rjes", corrected)
        self.assertIn("a b c d e f rkaṅ khal rṅa", corrected)
        self.assertIn("a b c d e zaṅ ziri gi 'bul", corrected)
        self.assertIn("a b c d e sṅar gyi ñams", corrected)
        self.assertIn("gtsaṅ khul mña' ris dan bcas kyi", corrected)
        self.assertIn("gźun don ses / las rnams mthon źiṅ gtsaṅ ba", corrected)
        reviewed_residual = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_residual_context_google"
        ]
        self.assertEqual(len(reviewed_residual), 10)
        pairs = {(row["from_token"], row["to_token"]) for row in reviewed_residual}
        self.assertIn(("sriar", "sṅar"), pairs)
        self.assertIn(("gtsani", "gtsaṅ"), pairs)
        self.assertIn(("nina", "mña"), pairs)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 12)

    def test_reviewed_tibetan_residual_context_cleanup_is_line_gated(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (229, 71): "a b c d e f rkani rjes",
                (229, 88): "a b c d e f rkani khal rria",
                (232, 22): "a b c d e zani ziri gi 'bul",
                (233, 70): "a b c d e sriar gi Nlams",
                (285, 68): "gtsani khul nina' ris dan bcas kyi",
                (362, 54): "giun don ses / las rnams mthon Zin gtsari ba",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("a b c d e f rkani rjes", corrected)
        self.assertIn("a b c d e f rkani khal rria", corrected)
        self.assertIn("a b c d e zani ziri gi 'bul", corrected)
        self.assertIn("a b c d e sriar gi Nlams", corrected)
        self.assertIn("gtsani khul nina' ris dan bcas kyi", corrected)
        self.assertIn("giun don ses / las rnams mthon Zin gtsari ba", corrected)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_residual_context_google"
            ]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_tibetan_ambitious_residual_cleanup_wts8_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (57, 43): "gañńs ti sei ~ byon",
                (94, 7): "Lex. i khuñń nam bu ga",
                (229, 12): 'Itar byuñń "welche sind jene',
                (247, 16): "bytu) zul byed de dper na chu la bya ba bźiń",
                (324, 47): "mo phag gi lo la sku khruñńs",
                (340, 61): "gsañń ba on chen skye",
                (370, 31): "1001); bañńs nas yar bton",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("gaṅs ti sei ~ byon", corrected)
        self.assertIn("Lex. i khuṅ nam bu ga", corrected)
        self.assertIn('ltar byuṅ "welche sind jene', corrected)
        self.assertIn("dper na chu la bya ba bźiṅ", corrected)
        self.assertIn("sku khruṅs", corrected)
        self.assertIn("gsaṅ ba on chen", corrected)
        self.assertIn("baṅs nas yar bton", corrected)
        reviewed_ambitious = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_ambitious_residual_context"
        ]
        self.assertEqual(len(reviewed_ambitious), 8)
        pairs = {(row["from_token"], row["to_token"]) for row in reviewed_ambitious}
        self.assertIn(("Itar", "ltar"), pairs)
        self.assertIn(("gañńs", "gaṅs"), pairs)
        self.assertIn(("khuñń", "khuṅ"), pairs)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 8)

    def test_reviewed_tibetan_ambitious_residual_cleanup_wts9_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (52, 67): "mes thugs dam biens pa' 'phro thams cad",
                (178, 75): "beiden Brüder Khyun-po Mu-khyuñń-rgyan",
                (198, 32): "Lex. tamab (Mvy 4552, Abt. graris can gi",
                (232, 51): "śes rnam par Ses pa rdzas $// yod dam ~",
                (233, 20): "śes tab — pa'i phun sum tshogs (metr.)",
                (233, 35): "anidra)' (Ahs 1.5.23d); dṅos dan drios —",
                (233, 74): "entsteht\" (KunK 55,10); yal ~ spraṅ por 'gro",
                (285, 53): "(Tär 186,9); dpur rgyab kyi — źus nas",
                (318, 32): "dari yid chad pa la'añń",
                (343, 34): "Lex. Zin saam sa Zin (brDa); źinń sa (Dagy).",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("mes thugs dam bźens pa' 'phro", corrected)
        self.assertIn("Mu-khyuṅ-rgyan", corrected)
        self.assertIn("graṅs can gyi", corrected)
        self.assertIn("śes rnam par śes pa rdzas $// yod", corrected)
        self.assertIn("śes rab — pa'i", corrected)
        self.assertIn("dṅos daṅ dṅos —", corrected)
        self.assertIn("yul ~ spraṅ por", corrected)
        self.assertIn("(Tār 186,9); dpun rgyab kyi", corrected)
        self.assertIn("dpun rgyab kyi", corrected)
        self.assertIn("daṅ yid chad pa la'aṅ", corrected)
        self.assertIn("Lex. źiṅ sa'am sa źiṅ (brDa); źiṅ sa", corrected)
        reviewed_ambitious = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_ambitious_residual_context"
        ]
        self.assertEqual(len(reviewed_ambitious), 16)
        pairs = {(row["from_token"], row["to_token"]) for row in reviewed_ambitious}
        self.assertIn(("biens", "bźens"), pairs)
        self.assertIn(("Mu-khyuñń-rgyan", "Mu-khyuṅ-rgyan"), pairs)
        self.assertIn(("la'añń", "la'aṅ"), pairs)
        self.assertIn(("Zin", "źiṅ"), pairs)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 17)

    def test_reviewed_tibetan_ambitious_residual_cleanup_is_line_gated(self) -> None:
        wts8_text = self.fixture_with_reviewed_lines(
            {
                (57, 44): "gañńs ti sei ~ byon",
                (229, 13): 'Itar byuñń "welche sind jene',
                (340, 62): "gsañń ba on chen skye",
            }
        )
        wts9_text = self.fixture_with_reviewed_lines(
            {
                (52, 68): "mes thugs dam biens pa' 'phro thams cad",
                (233, 36): "anidra)' (Ahs 1.5.23d); dṅos dan drios —",
                (343, 35): "Lex. Zin saam sa Zin (brDa); źinń sa (Dagy).",
            }
        )

        wts8_result, wts8_corrected, wts8_changes = self.run_postprocess_fixture(
            wts8_text,
            label="wts_8_b",
        )
        wts9_result, wts9_corrected, wts9_changes = self.run_postprocess_fixture(
            wts9_text,
            label="wts_9_m",
        )

        self.assertIn("gañńs ti sei ~ byon", wts8_corrected)
        self.assertIn('Itar byuñń "welche sind jene', wts8_corrected)
        self.assertIn("gsañń ba on chen skye", wts8_corrected)
        self.assertIn("biens pa' 'phro", wts9_corrected)
        self.assertIn("dṅos dan drios", wts9_corrected)
        self.assertIn("Zin saam sa Zin", wts9_corrected)
        self.assertFalse(
            [
                row
                for row in wts8_changes + wts9_changes
                if row["reason"] == "reviewed_tibetan_exact_ambitious_residual_context"
            ]
        )
        self.assertEqual(wts8_result["reviewed_tibetan_exact_changes"], 0)
        self.assertEqual(wts9_result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_tibetan_second_ambitious_cleanup_wts8_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (21, 30): "te — gtsan ma'i mchod sbyin",
                (31, 40): "blan dor 'od kyi snani ba ches gsal ba'i / —",
                (52, 18): "sran beu nas bco lna' —",
                (61, 60): "bar snani Kurzf. für bar gi snari ba.",
                (64, 55): "de bcom ldan 'das kyi spyan sriar ma phyin",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_8_b",
        )

        self.assertIn("te — gtsaṅ ma'i mchod sbyin", corrected)
        self.assertIn("blan dor 'od kyi snaṅ ba ches gsal ba'i / —", corrected)
        self.assertIn("sran beu nas bco lṅa' —", corrected)
        self.assertIn("bar snaṅ Kurzf. für bar gi snaṅ ba.", corrected)
        self.assertIn("de bcom ldan 'das kyi spyan sṅar ma phyin", corrected)
        reasons = {
            row["reason"]
            for row in changes
            if row["reason"].startswith("reviewed_tibetan_exact_second_ambitious_")
        }
        self.assertEqual(
            reasons,
            {
                "reviewed_tibetan_exact_second_ambitious_gtsang",
                "reviewed_tibetan_exact_second_ambitious_lnga",
                "reviewed_tibetan_exact_second_ambitious_snang",
                "reviewed_tibetan_exact_second_ambitious_sngar",
            },
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in changes
                    if row["reason"].startswith(
                        "reviewed_tibetan_exact_second_ambitious_"
                    )
                ]
            ),
            6,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_tibetan_second_ambitious_cleanup_wts9_examples(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (24, 67): "'dod chags — sogs / dug lna' dban ur 'gro",
                (32, 18): "— es bya ba'i ri la drios grub mchog thob",
                (75, 55): "gtsani ma' bris byugs la",
                (104, 61): "3. Bez. für den Raum; —r snari dass.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("'dod chags — sogs / dug lṅa' dban ur 'gro", corrected)
        self.assertIn("— es bya ba'i ri la dṅos grub mchog thob", corrected)
        self.assertIn("gtsaṅ ma' bris byugs la", corrected)
        self.assertIn("3. Bez. für den Raum; —r snaṅ dass.", corrected)
        reasons = {
            row["reason"]
            for row in changes
            if row["reason"].startswith("reviewed_tibetan_exact_second_ambitious_")
        }
        self.assertEqual(
            reasons,
            {
                "reviewed_tibetan_exact_second_ambitious_dngos",
                "reviewed_tibetan_exact_second_ambitious_gtsang",
                "reviewed_tibetan_exact_second_ambitious_lnga",
                "reviewed_tibetan_exact_second_ambitious_snang",
            },
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in changes
                    if row["reason"].startswith(
                        "reviewed_tibetan_exact_second_ambitious_"
                    )
                ]
            ),
            4,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 4)

    def test_reviewed_tibetan_second_ambitious_cleanup_is_line_gated(self) -> None:
        wts8_text = self.fixture_with_reviewed_lines(
            {
                (52, 19): "sran beu nas bco lna' —",
                (64, 56): "de bcom ldan 'das kyi spyan sriar ma phyin",
                (73, 38): "(Debn 217,5); —r sriar gyi srol de ka gzun",
            }
        )
        wts9_text = self.fixture_with_reviewed_lines(
            {
                (24, 68): "'dod chags — sogs / dug lna' dban ur 'gro",
                (32, 19): "— es bya ba'i ri la drios grub mchog thob",
                (75, 56): "gtsani ma' bris byugs la",
                (104, 60): "3. Bez. für den Raum; —r snari dass.",
            }
        )

        wts8_result, wts8_corrected, wts8_changes = self.run_postprocess_fixture(
            wts8_text,
            label="wts_8_b",
        )
        wts9_result, wts9_corrected, wts9_changes = self.run_postprocess_fixture(
            wts9_text,
            label="wts_9_m",
        )

        self.assertIn("bco lna' —", wts8_corrected)
        self.assertIn("spyan sriar ma phyin", wts8_corrected)
        self.assertIn("—r sriar gyi srol", wts8_corrected)
        self.assertIn("dug lna' dban", wts9_corrected)
        self.assertIn("drios grub", wts9_corrected)
        self.assertIn("gtsani ma' bris", wts9_corrected)
        self.assertIn("—r snari dass.", wts9_corrected)
        self.assertFalse(
            [
                row
                for row in wts8_changes + wts9_changes
                if row["reason"].startswith(
                    "reviewed_tibetan_exact_second_ambitious_"
                )
            ]
        )
        self.assertEqual(wts8_result["reviewed_tibetan_exact_changes"], 0)
        self.assertEqual(wts9_result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_tibetan_residual_error_family_exact_rows(self) -> None:
        wts8_text = self.fixture_with_reviewed_lines(
            {
                (117, 77): "— kyis'diltabuga la ses \"wie konnten die Ti-",
                (288, 17): "bdaggi btsun mo 'di ~ ñan pa 'diltabuszinna",
                (464, 42): "du yan d ños rtags dan mtshan ma dagkyań ~",
                (510, 62): "lus kyi nad rnam pa 'diltabi 'di dag 'byun ba",
                (510, 63): "'dilta ste ... 'bras dan / phol mig dan / — da",
            }
        )
        wts9_text = self.fixture_with_reviewed_lines(
            {
                (36, 50): "lba mo thams cad la / 'dilta ste spyan dan /",
                (190, 74): "mam par 'byed pa gaṅ ze na / 'dilta ste... -r",
                (333, 58): "ñas chos gdags pa rnam par bźag pa 'dilta ste",
            }
        )

        wts8_result, wts8_corrected, wts8_changes = self.run_postprocess_fixture(
            wts8_text,
            label="wts_8_b",
        )
        wts9_result, wts9_corrected, wts9_changes = self.run_postprocess_fixture(
            wts9_text,
            label="wts_9_m",
        )

        self.assertIn("— kyis 'di lta bu ga la ses", wts8_corrected)
        self.assertIn("bdaggi btsun mo 'di ~ ñan pa 'di lta bu źin na", wts8_corrected)
        self.assertIn("du yan d ños rtags dan mtshan ma dag kyaṅ ~", wts8_corrected)
        self.assertIn("lus kyi nad rnam pa 'di lta bu'i 'di dag 'byun ba", wts8_corrected)
        self.assertIn("'di lta ste ... 'bras dan / phol mig dan / — da", wts8_corrected)
        self.assertIn("lba mo thams cad la / 'di lta ste spyan dan /", wts9_corrected)
        self.assertIn("mam par 'byed pa gaṅ ze na / 'di lta ste... -r", wts9_corrected)
        self.assertIn("ñas chos gdags pa rnam par bźag pa 'di lta ste", wts9_corrected)

        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in wts8_changes + wts9_changes
        }
        self.assertIn(
            ("dagkyań", "dag kyaṅ", "reviewed_tibetan_exact_residual_spacing_ng"),
            reasons,
        )
        self.assertIn(
            ("dilta", "di lta", "reviewed_tibetan_exact_di_lta_spacing"),
            reasons,
        )
        self.assertIn(
            (
                "kyis'diltabuga",
                "kyis 'di lta bu ga",
                "reviewed_tibetan_exact_di_lta_bu_spacing",
            ),
            reasons,
        )
        self.assertIn(
            (
                "diltabuszinna",
                "di lta bu źin na",
                "reviewed_tibetan_exact_di_lta_bu_spacing",
            ),
            reasons,
        )
        self.assertIn(
            ("diltabi", "di lta bu'i", "reviewed_tibetan_exact_di_lta_bu_spacing"),
            reasons,
        )
        self.assertEqual(wts8_result["reviewed_tibetan_exact_changes"], 5)
        self.assertEqual(wts9_result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_tibetan_residual_error_family_is_line_gated(self) -> None:
        wts8_text = self.fixture_with_reviewed_lines(
            {
                (464, 43): "du yan d ños rtags dan mtshan ma dagkyań ~",
                (117, 78): "— kyis'diltabuga la ses \"wie konnten die Ti-",
                (288, 18): "bdaggi btsun mo 'di ~ ñan pa 'diltabuszinna",
                (510, 61): "lus kyi nad rnam pa 'diltabi 'di dag 'byun ba",
            }
        )
        wts9_text = self.fixture_with_reviewed_lines(
            {
                (36, 51): "lba mo thams cad la / 'dilta ste spyan dan /",
            }
        )

        wts8_result, wts8_corrected, wts8_changes = self.run_postprocess_fixture(
            wts8_text,
            label="wts_8_b",
        )
        wts9_result, wts9_corrected, wts9_changes = self.run_postprocess_fixture(
            wts9_text,
            label="wts_9_m",
        )

        self.assertIn("mtshan ma dagkyań ~", wts8_corrected)
        self.assertIn("kyis'diltabuga la ses", wts8_corrected)
        self.assertIn("'diltabuszinna", wts8_corrected)
        self.assertIn("'diltabi 'di dag", wts8_corrected)
        self.assertIn("'dilta ste spyan", wts9_corrected)
        self.assertFalse(
            [
                row
                for row in wts8_changes + wts9_changes
                if row["reason"]
                in {
                    "reviewed_tibetan_exact_residual_spacing_ng",
                    "reviewed_tibetan_exact_di_lta_spacing",
                    "reviewed_tibetan_exact_di_lta_bu_spacing",
                }
            ]
        )
        self.assertEqual(wts8_result["reviewed_tibetan_exact_changes"], 0)
        self.assertEqual(wts9_result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_bzhin_bzhugs_exact_rows_apply_only_on_reviewed_locations(self) -> None:
        wts8_text = self.fixture_with_reviewed_lines(
            {
                (15, 65): "rlun gzun ste yani ma gul bar bZugs pas",
                (50, 6): "bzugs pa die vier Gottheiten",
            }
        )
        wts9_text = self.fixture_with_reviewed_lines(
            {
                (13, 72): "bans lare ba - 09 par / Zal bzugs tsbe na",
                (49, 41): "rten gsum la sogs pa tshig don rnams la bZin nas",
            }
        )

        wts8_result, wts8_corrected, wts8_changes = self.run_postprocess_fixture(
            wts8_text,
            label="wts_8_b",
        )
        wts9_result, wts9_corrected, wts9_changes = self.run_postprocess_fixture(
            wts9_text,
            label="wts_9_m",
        )

        self.assertIn("ste yaṅ ma gul bar bźugs pas", wts8_corrected)
        self.assertIn("bźugs pa die vier", wts8_corrected)
        self.assertIn("Zal bźugs tsbe", wts9_corrected)
        self.assertIn("la bźin nas", wts9_corrected)

        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in wts8_changes + wts9_changes
        }
        self.assertIn(("bZugs", "bźugs", "reviewed_tibetan_exact_bzhin_bzhugs"), reasons)
        self.assertIn(("bzugs", "bźugs", "reviewed_tibetan_exact_bzhin_bzhugs"), reasons)
        self.assertIn(("bZin", "bźin", "reviewed_tibetan_exact_bzhin_bzhugs"), reasons)
        self.assertIn(("yani", "yaṅ", "reviewed_tibetan_exact_yang"), reasons)
        self.assertEqual(wts8_result["reviewed_tibetan_exact_changes"], 3)
        self.assertEqual(wts9_result["reviewed_tibetan_exact_changes"], 2)

    def test_reviewed_bzhin_bzhugs_exact_rows_do_not_generalize(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (1, 1): "rlun gzun ste yani ma gul bar bZugs pas",
                (1, 2): "sku gsum rnam par du bzugs pa",
                (1, 3): "rten gsum la sogs pa tshig don rnams la bZin nas",
                (1, 4): "(r. bZi) zhes bstan",
                (1, 5): "bzi ba dang bźi ba",
            }
        )

        _result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("ste yani ma gul bar bZugs pas", corrected)
        self.assertIn("du bzugs pa", corrected)
        self.assertIn("la bZin nas", corrected)
        self.assertIn("(r. bZi) zhes bstan", corrected)
        self.assertIn("bzi ba dang bźi ba", corrected)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_bzhin_bzhugs"
            ]
        )

    def test_reviewed_tar_siglum_exact_rows_apply_only_on_reviewed_locations(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (229, 63): "Tär 160,9; dpun rgyab kyi",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_9_m",
        )

        self.assertIn("Tār 160,9; dpun rgyab kyi", corrected)
        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in changes
        }
        self.assertIn(("Tär", "Tār", "reviewed_siglum_exact_tar"), reasons)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

        unreviewed_text = self.fixture_with_reviewed_lines(
            {
                (229, 64): "Tär 160,9; dpun rgyab kyi",
            }
        )

        _result, unreviewed_corrected, unreviewed_changes = self.run_postprocess_fixture(
            unreviewed_text,
            label="wts_9_m",
        )

        self.assertIn("Tär 160,9; dpun rgyab kyi", unreviewed_corrected)
        self.assertFalse(
            [
                row
                for row in unreviewed_changes
                if row["reason"] == "reviewed_siglum_exact_tar"
            ]
        )

    def test_reviewed_reference_marker_rows_apply_only_on_reviewed_locations(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (38, 13): "nna?) (Tshe 1b2); — = Ispros bral (Bon 18,13);",
                (380, 33): "གྲིམ་པོ་ grim po klug, geschickt; vgl. Isgrim po.",
                (674, 179): "Geschlechtsorgan, vgl. Ichos 'byun 3.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("— = ↓ spros bral", corrected)
        self.assertIn("vgl. ↓ sgrim po.", corrected)
        self.assertIn("vgl. ↑ chos 'byun 3.", corrected)
        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in changes
        }
        self.assertIn(
            ("Ispros", "↓ spros", "reviewed_tibetan_exact_reference_marker"),
            reasons,
        )
        self.assertIn(
            ("Isgrim", "↓ sgrim", "reviewed_tibetan_exact_reference_marker"),
            reasons,
        )
        self.assertIn(
            ("Ichos", "↑ chos", "reviewed_tibetan_exact_reference_marker"),
            reasons,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_reference_marker_row_can_consume_keyed_apostrophe_suffix(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (176, 10): "men, 1, 5, v. unterworfen werden; vgl. Tbka'",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_35_51",
        )

        self.assertIn("vgl. ↑ bka'", corrected)
        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in changes
        }
        self.assertIn(
            ("Tbka'", "↑ bka'", "reviewed_tibetan_exact_reference_marker"),
            reasons,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

    def test_reviewed_reference_marker_tchos_family_applies_only_on_exact_rows(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (675, 44): "ཆོས་སྐུ་ chos sku Tchos kyi sku.",
                (676, 93): "ཆོས་གྲགས་ chos grags Tchos kyi grags pa.",
                (679, 165): "ཆོས་སྤྲིན་ chos sprin Tchos kyi sprin.",
                (679, 166): "ཆོས་ཕུང་ chos phun Tchos kyi phuṅ po.",
                (680, 118): "ཆོས་བརིགས་ chos brtsigs Tchos rtsig.",
                (680, 119): "Tchos on an adjacent unreviewed line stays unchanged.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertEqual(corrected.count("↑ chos"), 5)
        self.assertIn("Tchos on an adjacent unreviewed line stays unchanged.", corrected)
        marker_changes = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_reference_marker"
        ]
        self.assertEqual(len(marker_changes), 5)
        self.assertIn("ཆོས་ཕུང་ chos phuṅ ↑ chos kyi phuṅ po.", corrected)
        self.assertTrue(
            all(
                (row["from_token"], row["to_token"]) == ("Tchos", "↑ chos")
                for row in marker_changes
            )
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_reference_marker_tran_row_applies_only_at_exact_location(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (543, 138): "2. schlecht, vgl. Tran pa.",
                (543, 139): "An adjacent Tran string stays unchanged.",
                (758, 184): "ཉངས་ Hans Tran po.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("vgl. ↓ raṅ pa.", corrected)
        self.assertIn("An adjacent Tran string stays unchanged.", corrected)
        self.assertIn("ཉངས་ ñaṅs ↓ raṅ po.", corrected)
        marker_changes = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_reference_marker"
        ]
        self.assertEqual(
            [
                (row["from_token"], row["to_token"])
                for row in marker_changes
            ],
            [("Tran", "↓ raṅ"), ("Tran", "↓ raṅ")],
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_reference_marker_backslash_residual_family_is_exact(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (155, 92): "མཀར་བུ་ mkar bu \\mkhar bu.",
                (246, 203): "།བ་ད་ kha da \\tsha kha da.",
                (600, 173): (
                    "Lex. kham gan gi tshod du bcad pa’i zas sogs "
                    "བཅད་མཆམས་ bcad mtshams \\dpyad mishams."
                ),
                (981, 19): "\\dbyar zla tha chun; ~ bźi die jeweils letzten",
                (488, 114): "རྒྱང་ rgyon pf. \\brgyans fut. \\brgyan imp.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        for expected in [
            "mkar bu ↓ mkhar bu.",
            "kha da ↓ tsha kha da.",
            "bcad mtshams ↓ dpyad mishams.",
            "↓ dbyar zla tha chuṅ",
        ]:
            self.assertIn(expected, corrected)
        self.assertIn("pf. \\brgyans fut. \\brgyan imp.", corrected)
        marker_changes = [
            (row["from_token"], row["to_token"])
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_reference_marker"
        ]
        self.assertEqual(
            marker_changes,
            [
                ("\\mkhar", "↓ mkhar"),
                ("\\tsha", "↓ tsha"),
                ("\\dpyad", "↓ dpyad"),
                ("\\dbyar", "↓ dbyar"),
            ],
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 5)

    def test_reviewed_reference_marker_tbrgya_row_is_exact(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (510, 77): "བརྒྱ་སྦྱིན་ braya sbyin Tbrgya byin 1.",
                (510, 78): "An adjacent Tbrgya string stays unchanged.",
                (518, 58): "བསྒྱུན་ bsgrun pf. und fut. zu Tsgrun wettei-",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("braya sbyin ↑ brgya byin 1.", corrected)
        self.assertIn("An adjacent Tbrgya string stays unchanged.", corrected)
        self.assertIn("zu Tsgrun wettei-", corrected)
        marker_changes = [
            (row["from_token"], row["to_token"])
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_reference_marker"
        ]
        self.assertEqual(marker_changes, [("Tbrgya", "↑ brgya")])
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

    def test_reviewed_reference_marker_backslash_rows_require_exact_boundary(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (139, 112): "one two \\bka’ still exact.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("one two ↓ bka’ still exact.", corrected)
        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in changes
        }
        self.assertIn(
            ("\\bka’", "↓ bka’", "reviewed_tibetan_exact_reference_marker"),
            reasons,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

        embedded_text = self.fixture_with_reviewed_lines(
            {
                (139, 112): "one two I\\bka’ embedded prefix should stay.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            embedded_text,
            label="wts_1_34",
        )

        self.assertIn("one two I\\bka’ embedded prefix should stay.", corrected)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_reference_marker"
            ]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_reference_marker_match_options_include_spaced_marker(self) -> None:
        line = "vgl. / chos sku und \\ bka"
        chos_start = line.index("chos")
        chos_end = chos_start + len("chos")
        chos_options = pem.reviewed_tibetan_exact_match_options(line, "chos", chos_start, chos_end)

        self.assertIn(("/ chos", line.index("/"), chos_end), chos_options)

        bka_start = line.index("bka")
        bka_end = bka_start + len("bka")
        bka_options = pem.reviewed_tibetan_exact_match_options(line, "bka", bka_start, bka_end)

        self.assertIn(("\\ bka", line.index("\\"), bka_end), bka_options)

    def test_reviewed_reference_marker_rows_do_not_create_broad_marker_rules(self) -> None:
        unreviewed_text = self.fixture_with_reviewed_lines(
            {
                (38, 14): "nna?) (Tshe 1b2); — = Ispros bral remains unreviewed.",
                (327, 128): "འཁང་ག་ 'khran ga hart, fest; vgl. Tmkhran ba remains unreviewed.",
                (200, 20): "gser-Idan mThon-ba don-Idan śugs-Idan stay compounds.",
                (201, 21): "/gan \\gan Igan Tgan stay diagnostic only.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            unreviewed_text,
            label="wts_1_34",
        )

        self.assertIn("— = Ispros bral remains unreviewed.", corrected)
        self.assertIn("vgl. Tmkhran ba remains unreviewed.", corrected)
        self.assertIn(
            "gser-Idan mThon-ba don-Idan śugs-Idan stay compounds.",
            corrected,
        )
        self.assertIn("/gan \\gan Igan Tgan stay diagnostic only.", corrected)
        self.assertFalse(
            [
                row
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_reference_marker"
            ]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_reviewed_script_ng_witness_rows_apply_only_on_reviewed_locations(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (338, 85): "གང་དང་ཡང་ gan daṅ yaṅ gan yan.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("གང་དང་ཡང་ gaṅ daṅ yaṅ gaṅ yaṅ.", corrected)
        reasons = {
            (row["from_token"], row["to_token"], row["reason"])
            for row in changes
        }
        self.assertIn(
            ("gan", "gaṅ", "reviewed_tibetan_exact_script_ng_witness"),
            reasons,
        )
        self.assertIn(
            ("yan", "yaṅ", "reviewed_tibetan_exact_script_ng_witness"),
            reasons,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

        unreviewed_text = self.fixture_with_reviewed_lines(
            {
                (338, 86): "གང་དང་ཡང་ gan daṅ yaṅ gan yan.",
            }
        )

        _result, unreviewed_corrected, unreviewed_changes = self.run_postprocess_fixture(
            unreviewed_text,
            label="wts_1_34",
        )

        self.assertIn("གང་དང་ཡང་ gan daṅ yaṅ gan yan.", unreviewed_corrected)
        self.assertFalse(
            [
                row
                for row in unreviewed_changes
                if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            ]
        )

    def test_reviewed_exact_can_consume_keyed_dotless_i_suffix(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (338, 83): "གང་དག་ 4927? dag Tganı 3.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("གང་དག་ 4927? dag ↑ gaṅ 3.", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
        ]
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["from_token"], "Tganı")
        self.assertEqual(reviewed[0]["to_token"], "↑ gaṅ")
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

    def test_reviewed_script_ng_residual_rows_apply_only_when_reviewed(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (52, 135): "a b ran",
                (568, 1): "snar",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("a b raṅ", corrected)
        self.assertIn("sṅar", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
        ]
        self.assertEqual(
            {(row["from_token"], row["to_token"]) for row in reviewed},
            {
                ("ran", "raṅ"),
                ("snar", "sṅar"),
            },
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 2)

        deferred_text = self.fixture_with_reviewed_lines(
            {
                (543, 114): "dan 'then",
                (1111, 21): "a b c d e Tdan",
            }
        )

        _result, deferred_corrected, deferred_changes = self.run_postprocess_fixture(
            deferred_text,
            label="wts_1_34",
        )

        self.assertIn("dan 'then", deferred_corrected)
        self.assertIn("a b c d e Tdan", deferred_corrected)
        self.assertFalse(
            [
                row
                for row in deferred_changes
                if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            ]
        )

    def test_reviewed_tibetan_script_final_ng_seed_rows_are_exact(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (758, 184): "ཉངས་ Hans Tran po.",
                (981, 19): "↓ dbyar zla tha chun; ~ bźi die jeweils letzten",
                (981, 18): "Iston zla tha chun, \\dpyid zla tha chun,",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("ཉངས་ ñaṅs ↓ raṅ po.", corrected)
        self.assertIn(
            "↓ dbyar zla tha chuṅ; ~ bźi die jeweils letzten",
            corrected,
        )
        self.assertIn("Iston zla tha chun, \\dpyid zla tha chun,", corrected)
        reviewed = {
            (row["page"], row["line"], row["from_token"], row["to_token"], row["reason"])
            for row in changes
            if row["tier"] == "reviewed_tibetan_exact"
        }
        self.assertIn(
            (
                "758",
                "184",
                "Hans",
                "ñaṅs",
                "reviewed_tibetan_exact_script_ng_witness",
            ),
            reviewed,
        )
        self.assertIn(
            (
                "758",
                "184",
                "Tran",
                "↓ raṅ",
                "reviewed_tibetan_exact_reference_marker",
            ),
            reviewed,
        )
        self.assertIn(
            (
                "981",
                "19",
                "chun",
                "chuṅ",
                "reviewed_tibetan_exact_final_ng",
            ),
            reviewed,
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_chung_headword_batch_is_exact(self) -> None:
        reviewed_lines = {
            (56, 115): "ཀུ་བ་ཆུང་བ་ ku ba chun ba",
            (56, 117): "ཀུ་བ་ཆུང་བ་ ku ba chun ba Bilva-Baum und Bilva-",
            (60, 101): "ཀུ་ས་ལི་ཆུང་བ་ ku sa li chun ba",
            (99, 86): "ཀོན་པ་གབ་ཆུང་ kon pa gab chun eine Heilpflanze,",
            (114, 8): "ཀླུ་སྒྲུལ་འོད་ཆུང་ klu sbrul ’od chun auch klu sbrul",
            (114, 54): "ཀླུ་མེས་འབྲོམ་ཆུང་པ་ klu mes 'brom chun pa npr. ein",
            (56, 116): "An unreviewed prose chun stays unchanged.",
        }

        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(reviewed_lines),
            label="wts_1_34",
        )

        for line in reviewed_lines.values():
            if "ཆུང" in line:
                self.assertIn(line.replace("chun", "chuṅ"), corrected)
        self.assertIn("An unreviewed prose chun stays unchanged.", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            and row["from_token"] == "chun"
        ]
        self.assertEqual(len(reviewed), 6)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_chung_direct_batch_changes_only_exact_tokens(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (121, 151): "དཀར་ཆུང་རིང་མོ་ dkar chun rin mo",
                (256, 61): "།ཁ་སཱན་ཆུང་ངུ་ kha sran chun hu ein Getreide.",
                (408, 51): "དགུན་ཟླ་བ་ཆུང dgun zla tha chun",
                (408, 52): "An unreviewed prose chun and hu stay unchanged.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("dkar chuṅ riṅ mo", corrected)
        self.assertIn("kha sran chuṅ ṅu ein Getreide.", corrected)
        self.assertIn("dgun zla tha chuṅ", corrected)
        self.assertIn("An unreviewed prose chun and hu stay unchanged.", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            and row["from_token"] == "chun"
        ]
        self.assertEqual(len(reviewed), 3)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 5)

    def test_reviewed_ngu_seed_is_exact_and_does_not_change_sran(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (256, 61): "།ཁ་སཱན་ཆུང་ངུ་ kha sran chuṅ hu ein Getreide.",
                (256, 62): "An unrelated hu stays unchanged.",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )

        self.assertIn("kha sran chuṅ ṅu ein Getreide.", corrected)
        self.assertIn("An unrelated hu stays unchanged.", corrected)
        self.assertNotIn("kha srān", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            and row["from_token"] == "hu"
        ]
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["to_token"], "ṅu")
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)

    def test_reviewed_direct_unique_final_ng_batch_is_exact(self) -> None:
        reviewed_lines = {
            (491, 157): "སྒེའུ་ཆུང་ sge’u chun",
            (503, 71): "སྒྲུང་ sgrun Erzählung, Geschichtenerzähler.",
            (561, 22): "ཇྭའུ་ཆུང་ rha’u chun eine kleine Trommel, vgl.",
            (760, 107): "ཉམ་ཆུང་དབང་པོ་ nam chun dban po",
            (1066, 95): "མཐོང་ཆུང་བ་ mthon chun ba geringes Anse-",
            (1066, 96): "Unreviewed chun, sgrun, and rha’u stay unchanged.",
        }

        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(reviewed_lines),
            label="wts_1_34",
        )

        self.assertIn("sge’u chuṅ", corrected)
        self.assertIn("sgruṅ Erzählung", corrected)
        self.assertIn("rha’u chuṅ", corrected)
        self.assertIn("nam chuṅ dbaṅ po", corrected)
        self.assertIn("mthoṅ chuṅ ba", corrected)
        self.assertIn(
            "Unreviewed chun, sgrun, and rha’u stay unchanged.",
            corrected,
        )
        self.assertEqual(
            {
                (row["from_token"], row["to_token"])
                for row in changes
                if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
            },
            {("chun", "chuṅ"), ("sgrun", "sgruṅ")},
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 7)

    def test_reviewed_repeated_lemma_final_ng_batch_is_exact(self) -> None:
        reviewed_lines = {
            (60, 118): "ཀུ་ས་ལི་ཆུང་བ་ ku sa li chun ba, auch ku sa li chun",
            (587, 65): "ཅོལ་ཆུང་ col chun auch col re chun, gcol chun",
            (617, 44): "ལྩེའུ་ཆུང་ /©6¢ chun auch lce chun Gaumen-",
            (766, 16): "ཉམས་ཆུང་ ༩༩༩༠ chun \\nam chun.",
            (1028, 9): "ཐེའུ་ཆུང་ the’n chun lmthe’u chun.",
            (1028, 10): "Unreviewed chun and damaged prefixes stay unchanged.",
        }

        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(reviewed_lines),
            label="wts_1_34",
        )

        self.assertIn("ku sa li chuṅ ba, auch ku sa li chuṅ", corrected)
        self.assertIn("col chuṅ auch col re chuṅ, gcol chuṅ", corrected)
        self.assertIn("/©6¢ chuṅ auch lce chuṅ", corrected)
        self.assertIn("༩༩༩༠ chuṅ \\nam chuṅ", corrected)
        self.assertIn("the’n chuṅ lmthe’u chuṅ", corrected)
        self.assertIn(
            "Unreviewed chun and damaged prefixes stay unchanged.",
            corrected,
        )
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
        ]
        self.assertEqual(len(reviewed), 11)
        self.assertEqual(
            {(row["from_token"], row["to_token"]) for row in reviewed},
            {("chun", "chuṅ")},
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 11)

    def test_reviewed_manual_alignment_final_ng_batch_is_exact(self) -> None:
        reviewed_lines = {
            (337, 54): "གང་ག་ཆུང་ gar ga chun",
            (551, 114): "མངོན་ཆུང་ mnon chun",
            (657, 1): 'ཆུང་གྲས\" chun gras',
            (827, 115): "སྙོམས་ཆུང་ säoms chun",
            (1160, 32): "དུད་ཆུང་ dud chun Steuer zahlender Bauer,",
            (1160, 33): "Unreviewed gar, mnon, and chun stay unchanged.",
        }

        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(reviewed_lines),
            label="wts_1_34",
        )

        self.assertIn("gar ga chuṅ", corrected)
        self.assertIn("mnon chuṅ", corrected)
        self.assertIn('ཆུང་གྲས\" chuṅ gras', corrected)
        self.assertIn("säoms chuṅ", corrected)
        self.assertIn("dud chuṅ Steuer", corrected)
        self.assertIn(
            "Unreviewed gar, mnon, and chun stay unchanged.",
            corrected,
        )
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
        ]
        self.assertEqual(len(reviewed), 5)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 5)

    def test_reviewed_damaged_context_final_ng_tokens_are_independent(self) -> None:
        reviewed_lines = {
            (491, 208): "SQ ཆུང་ 'sge’n chun }'sge’n.",
            (659, 3): "ཆུང་ཆུང་ chun chun klein, sehr klein.",
            (659, 22): "ཆུང་སྟག་ chun /¡7£ zweitjüngster.",
            (823, 1): "སྙིང་ཕོད་ཆུང་བ་ 4?7//7 phod chun ba",
            (981, 58): "ཐ་ཆུང་རྨུ་ལྟམ་ཐང་མོ་སྨན་ 77% chun )7?7// Ilcam",
        }

        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(reviewed_lines),
            label="wts_1_34",
        )

        self.assertIn("'sge’n chuṅ }'sge’n", corrected)
        self.assertIn("chuṅ chuṅ klein", corrected)
        self.assertIn("chuṅ /¡7£", corrected)
        self.assertIn("4?7//7 phod chuṅ ba", corrected)
        self.assertIn("77% chuṅ )7?7// Ilcam", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
        ]
        self.assertEqual(len(reviewed), 6)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_dban_consensus_rows_are_exact(self) -> None:
        fixtures = {
            "wts_1_34": {
                (52, 81): "ཀརྨ་བསྟན་སྐྱོང་དབང་པོ་ karma bstan skyon dban po",
                (52, 82): "A bibliographic dban and unrelated prose dban stay unchanged.",
            },
            "wts_8_b": {
                (352, 41): 'དབང་པོ་ "dban po',
                (352, 42): "Plain dban without the reviewed row stays unchanged.",
            },
        }
        for label, lines in fixtures.items():
            with self.subTest(label=label):
                result, corrected, changes = self.run_postprocess_fixture(
                    self.fixture_with_reviewed_lines(lines),
                    label=label,
                )
                self.assertIn("dbaṅ po", corrected)
                self.assertIn("dban", corrected)
                reviewed = [
                    row
                    for row in changes
                    if row["reason"] == "reviewed_tibetan_exact_final_ng_consensus"
                    and row["from_token"] == "dban"
                ]
                self.assertEqual(len(reviewed), 1)
                self.assertEqual(reviewed[0]["from_token"], "dban")
                self.assertEqual(reviewed[0]["to_token"], "dbaṅ")
                self.assertEqual(
                    result["reviewed_tibetan_exact_changes"],
                    2 if label == "wts_1_34" else 1,
                )

    def test_reviewed_rkan_consensus_rows_are_exact(self) -> None:
        reviewed_text = self.fixture_with_reviewed_lines(
            {
                (155, 188): "རྐང་ཀོར་ rkan kor Fußschmuck, Fußring.",
                (156, 201): "རྐང་གཉིས་ rkan 677/5 Mensch; — mchog, — dam",
                (156, 202): "German and bibliographic rkan remain unchanged.",
            }
        )
        result, corrected, changes = self.run_postprocess_fixture(
            reviewed_text,
            label="wts_1_34",
        )
        self.assertIn("rkaṅ kor", corrected)
        self.assertIn("rkaṅ 677/5", corrected)
        self.assertIn(
            "German and bibliographic rkan remain unchanged.",
            corrected,
        )
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_final_ng_consensus"
        ]
        self.assertEqual(len(reviewed), 2)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 2)

    def test_reviewed_cross_volume_residual_chung_rows_are_exact(self) -> None:
        fixtures = {
            "wts_35_51": {
                (361, 8): "ན་ག་ཆུང་ raga chun lṅa kha chun.",
                (633, 2): "སྣང་ཆུང་ chun.",
            },
            "wts_8_b": {
                (212, 42): "བྱིས་ཆུང་ 'byis chuṅ auch byis pa chun rn klei-",
                (529, 25): "སྤག་ཆུང་ sbag chun.",
            },
        }
        expected_counts = {"wts_35_51": 3, "wts_8_b": 2}
        for label, lines in fixtures.items():
            with self.subTest(label=label):
                result, corrected, changes = self.run_postprocess_fixture(
                    self.fixture_with_reviewed_lines(lines),
                    label=label,
                )
                self.assertNotIn(" chun", corrected)
                reviewed = [
                    row
                    for row in changes
                    if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
                ]
                self.assertEqual(len(reviewed), expected_counts[label])
                self.assertEqual(
                    result["reviewed_tibetan_exact_changes"],
                    expected_counts[label],
                )

    def test_reviewed_thang_consensus_rows_preserve_mixed_n_controls(self) -> None:
        lines = {
            (140, 14): "བཀའ་ཐང་ bka’ than alttib. bka’ tan Erlaß.",
            (360, 30): "གོང་ཐང་ gon than Preis, Wert.",
            (989, 131): "ཐང་ཐང་གྱེར་མཁས་ than than gyer mkhas Bez.",
            (989, 136): "ཐང་ཐན་ than than sehr klein, mickrig.",
            (988, 91): "ཐྲང་དཀར་ than dkar auch than kar.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("བཀའ་ཐང་ bka’ thaṅ alttib. bka’ tan", corrected)
        self.assertIn("གོང་ཐང་ goṅ thaṅ Preis", corrected)
        self.assertIn("ཐང་ཐང་གྱེར་མཁས་ thaṅ thaṅ gyer mkhas", corrected)
        self.assertIn("ཐང་ཐན་ thaṅ than sehr klein", corrected)
        self.assertIn("ཐྲང་དཀར་ than dkar auch than kar", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"] == "reviewed_tibetan_exact_final_ng_consensus"
            and row["from_token"] == "than"
            and row["to_token"] == "thaṅ"
        ]
        self.assertEqual(len(reviewed), 5)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_thang_rows_preserve_later_damage(self) -> None:
        lines = {
            (107, 3): "ཀྱས་ཐང་ལ་ kyus than la npr. Kloster in 2 1531",
            (199, 164): "སྐྱིན་ཐང་ skyin than auch skyin dan, skyin 777",
            (988, 197): "ཐང་ག་ than ga 1//77/7 ka 2,",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("kyus thaṅ la npr. Kloster in 2 1531", corrected)
        self.assertIn("skyin thaṅ auch skyin dan, skyin 777", corrected)
        self.assertIn("ཐང་ག་ thaṅ ga 1//77/7 ka 2,", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)
        self.assertEqual(
            sum(
                row["from_token"] == "than" and row["to_token"] == "thaṅ"
                for row in changes
            ),
            3,
        )

    def test_reviewed_khang_rows_preserve_neighbouring_n_families(self) -> None:
        lines = {
            (628, 48): "ཆང་།ཁང་ chan khan Wirtshaus.",
            (948, 109): "སྟེང་ཁང་ sten khan",
            (1159, 51): "དུད་ཁང་ dud khan Badehaus; vgl. [%//95 khan,",
            (1322, 1): "དྲི་བཟང་ཁང་ dri bzan khan",
            (600, 1): "མཁན་ mkhan genuine agentive form.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("ཆང་།ཁང་ chaṅ khaṅ Wirtshaus.", corrected)
        self.assertIn("སྟེང་ཁང་ steṅ khaṅ", corrected)
        self.assertIn("dud khaṅ Badehaus; vgl. [%//95 khan,", corrected)
        self.assertIn("དྲི་བཟང་ཁང་ dri bzaṅ khaṅ", corrected)
        self.assertIn("མཁན་ mkhan genuine agentive form.", corrected)
        reviewed = [
            row
            for row in changes
            if row["from_token"] == "khan" and row["to_token"] == "khaṅ"
        ]
        self.assertEqual(len(reviewed), 4)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 7)

    def test_reviewed_gong_rows_preserve_repetitions_and_neighbours(self) -> None:
        lines = {
            (360, 4): "གོང་གོང་ gon gon rund.",
            (360, 20): "གོང་གཉའ་ gon £77° Nacken, Oberes.",
            (360, 30): "གོང་ཐང་ gon thaṅ Preis, Wert.",
            (360, 143): "གོང་པོ་ ’gon po Kragen; vgl. Igor ba.",
            (361, 1): "གོང་མ་གོང་མ་ gon ma gon ma",
            (361, 50): "གོང་མའི་གོང་མ་ gon ma’i gon ma auch gon ma",
            (1116, 44): "དན་གོང་ dan gon auch dan kon Kugelbogen,",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("གོང་གོང་ goṅ goṅ rund.", corrected)
        self.assertIn("གོང་གཉའ་ goṅ £77°", corrected)
        self.assertIn("གོང་ཐང་ goṅ thaṅ", corrected)
        self.assertIn("གོང་པོ་ ’goṅ po", corrected)
        self.assertIn("གོང་མ་གོང་མ་ goṅ ma goṅ ma", corrected)
        self.assertIn("གོང་མའི་གོང་མ་ goṅ ma’i goṅ ma", corrected)
        self.assertIn("དན་གོང་ dan goṅ auch dan kon", corrected)
        reviewed = [
            row
            for row in changes
            if row["to_token"] == "goṅ"
            and row["reason"] == "reviewed_tibetan_exact_final_ng_consensus"
        ]
        self.assertEqual(len(reviewed), 10)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 10)

    def test_reviewed_goh_variant_maps_to_gong(self) -> None:
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(
                {(425, 6): "ནམ་གོང་ nam goh Bez. für das Mondhaus sa ri."}
            ),
            label="wts_35_51",
        )
        self.assertIn("ནམ་གོང་ nam goṅ Bez.", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)
        self.assertEqual(changes[-1]["from_token"], "goh")

    def test_prefixed_agong_rows_preserve_apostrophe_style(self) -> None:
        lines = {
            (397, 112): "གླད་འགོང་ glud ’gon eine Zeremonie zu Neu-",
            (439, 158): "འགོང་པོ་ ’gon po",
            (470, 89): "རྒྱལ་འགོང་ rgyal 'gon eine Dämonenart.",
            (439, 200): "འགང་པ gon po ein Damon; gon mo eine",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("གླད་འགོང་ glud ’goṅ", corrected)
        self.assertIn("འགོང་པོ་ ’goṅ po", corrected)
        self.assertIn("རྒྱལ་འགོང་ rgyal 'goṅ", corrected)
        self.assertIn("འགང་པ gon po ein Damon; gon mo", corrected)
        reviewed = [
            row
            for row in changes
            if row["reason"]
            == "reviewed_tibetan_exact_prefixed_final_ng_consensus"
        ]
        self.assertEqual(len(reviewed), 3)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 3)

    def test_reviewed_stong_rows_exclude_genuine_ston(self) -> None:
        lines = {
            (157, 58): "རྐང་སྟོང་སྐྱེལ་ rkaṅ ston skyel",
            (628, 206): "ཆང་པ་སྟོང་པ་ chan pa ston pa",
            (950, 164): "སྟོང་ 'ston",
            (952, 171): "སྟོང་གཉེར་ ston 97707ˆ",
            (953, 122): "སྟོང་གསུམ་ ston gsum 1000),",
            (200, 1): "དགའ་སྟོན་ dga’ ston Freudenfest.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("རྐང་སྟོང་སྐྱེལ་ rkaṅ stoṅ skyel", corrected)
        self.assertIn("ཆང་པ་སྟོང་པ་ chaṅ pa stoṅ pa", corrected)
        self.assertIn("སྟོང་ 'stoṅ", corrected)
        self.assertIn("སྟོང་གཉེར་ stoṅ 97707ˆ", corrected)
        self.assertIn("སྟོང་གསུམ་ stoṅ gsum 1000),", corrected)
        self.assertIn("དགའ་སྟོན་ dga’ ston Freudenfest.", corrected)
        reviewed = [
            row for row in changes
            if row["from_token"] == "ston" and row["to_token"] == "stoṅ"
        ]
        self.assertEqual(len(reviewed), 5)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_kong_rows_preserve_distinct_syllables(self) -> None:
        lines = {
            (97, 19): "ཀོང་ཀོང་ kon kon ausgehöhlt.",
            (97, 111): "ཀོང་རྗེ་བྲང་དཀར་ kon rje bran dkar",
            (98, 118): "ཀོང་ཙེ་ kon tse auch koṅ rtse, koṅ tshe.",
            (98, 104): "901,3). ཀོང་མོ་ 'kon mo tiefe Höhle.",
            (200, 1): "ཀོན་པ་ kon pa Bedeutung unklar.",
            (201, 1): "ཁོང་ khon pron. 3. pers.",
            (202, 1): "རྐོང་ rkon po.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("ཀོང་ཀོང་ koṅ koṅ", corrected)
        self.assertIn("ཀོང་རྗེ་བྲང་དཀར་ koṅ rje braṅ dkar", corrected)
        self.assertIn("ཀོང་ཙེ་ koṅ tse auch koṅ rtse, koṅ tshe.", corrected)
        self.assertIn("901,3). ཀོང་མོ་ 'koṅ mo", corrected)
        self.assertIn("ཀོན་པ་ kon pa", corrected)
        self.assertIn("ཁོང་ khon", corrected)
        self.assertIn("རྐོང་ rkon", corrected)
        reviewed = [
            row for row in changes
            if row["from_token"] == "kon" and row["to_token"] == "koṅ"
        ]
        self.assertEqual(len(reviewed), 5)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 6)

    def test_reviewed_glang_rows_preserve_neighbouring_damage_and_genuine_glan(self) -> None:
        lines = {
            (393, 183): "གླང་ཐབས་ glan thabs auch glan ’thab eine Er-",
            (393, 191): "གླང་འཐབ་ glan ’thab †2/%7 thabs.",
            (394, 196): "གླང་པོའི་གདོང་ glan po’i gdon Bez. für Ganesa.",
            (395, 57): "གླང་ཤིང་ glan sin ein Baum, Gebirgsweide.",
            (1275, 1): "དོམ་མགོ་གླང་སྙིང་ dom mgo glan sin",
            (1171, 1): "གླན་ glan genuine distinct syllable.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines),
            label="wts_1_34",
        )
        self.assertIn("གླང་ཐབས་ glaṅ thabs auch glaṅ ’thab", corrected)
        self.assertIn("གླང་འཐབ་ glaṅ ’thab †2/%7 thabs.", corrected)
        self.assertIn("གླང་པོའི་གདོང་ glaṅ po’i gdoṅ", corrected)
        self.assertIn("གླང་ཤིང་ glaṅ siṅ", corrected)
        self.assertIn("dom mgo glaṅ sin", corrected)
        self.assertIn("གླན་ glan genuine distinct syllable.", corrected)
        reviewed = [
            row for row in changes
            if row["from_token"] == "glan" and row["to_token"] == "glaṅ"
        ]
        self.assertEqual(len(reviewed), 6)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 8)

    def test_reviewed_glah_variant_maps_to_glang(self) -> None:
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(
                {(39, 51): "བན་གླང་མོ་ ban glah mo Ibal glari mo."}
            ),
            label="wts_8_b",
        )
        self.assertIn("བན་གླང་མོ་ ban glaṅ mo Ibal glari mo.", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)
        self.assertEqual(changes[-1]["from_token"], "glah")

    def test_reviewed_glang_echo_preserves_neighbouring_damage(self) -> None:
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(
                {(68, 56): "བལ་གླང་མོ་ bal glaṅ no auch ban glan mo Ele-"}
            ),
            label="wts_8_b",
        )
        self.assertIn("bal glaṅ no auch ban glaṅ mo", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 1)
        self.assertEqual(changes[-1]["reason"], "reviewed_tibetan_exact_final_ng_echo")

    def test_reviewed_bzang_rows_and_echo_preserve_genuine_bzan(self) -> None:
        lines = {
            (86, 60): "ཀུན་བཟང་མ་ kun bzan ma, auch kun bzan mo npr.",
            (987, 88): "ཐྲགས་བཟང་ thags bzan auch thag bzan wohl-",
            (200, 1): "བཟན་ bzan genuine distinct syllable.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kun bzaṅ ma, auch kun bzaṅ mo", corrected)
        self.assertIn("thags bzaṅ auch thag bzaṅ", corrected)
        self.assertIn("བཟན་ bzan genuine distinct syllable.", corrected)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 4)
        self.assertEqual(sum(row["to_token"] == "bzaṅ" for row in changes), 4)

    def test_reviewed_dung_rows_preserve_neighbouring_final_n_families(self) -> None:
        lines = {
            (1087, 34): "ད་དུང་ཀྱང་ da dun kyan Ida dun yan.",
            (1156, 24): "དུང་སྐྱོང་ dun skyon auch dun skyons npr.",
            (1156, 70): "དུང་རིང་ dun rin",
            (157, 136): "རྐང་དུང་ rkaṅ dun",
            (200, 1): "དུན་ dun genuine distinct syllable.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("da duṅ kyaṅ Ida dun yan", corrected)
        self.assertIn("duṅ skyoṅ auch duṅ skyons", corrected)
        self.assertIn("duṅ rin", corrected)
        self.assertIn("rkaṅ duṅ", corrected)
        self.assertIn("དུན་ dun genuine distinct syllable.", corrected)
        self.assertEqual(sum(row["to_token"] == "duṅ" for row in changes), 5)

    def test_reviewed_gling_rows_preserve_neighbouring_genuine_n(self) -> None:
        lines = {
            (945, 1): "སྟན་གླིང་པ་ stan glin pa",
            (1067, 75): "མཐོང་སྨོན་གླིང་ mthon smon glin npr. ein Ort.",
            (200, 1): "གླིན་ glin genuine distinct syllable.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("stan gliṅ pa", corrected)
        self.assertIn("mthoṅ smon gliṅ", corrected)
        self.assertIn("གླིན་ glin genuine distinct syllable.", corrected)
        self.assertEqual(sum(row["to_token"] == "gliṅ" for row in changes), 2)

    def test_reviewed_chang_rows_preserve_stong_and_distinct_forms(self) -> None:
        lines = {
            (628, 206): "ཆང་པ་སྟོང་པ་ chan pa stoṅ pa",
            (628, 72): "ཆང་འགག་ chan ’gag auch chan ’gags.",
            (200, 1): "ཆན་ chan genuine distinct syllable.",
            (201, 1): "འཆང་ ’chan separate prefixed family.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("chaṅ pa stoṅ pa", corrected)
        self.assertIn("chaṅ ’gag auch chaṅ ’gags", corrected)
        self.assertIn("ཆན་ chan genuine distinct syllable.", corrected)
        self.assertIn("འཆང་ ’chan separate prefixed family.", corrected)
        self.assertEqual(sum(row["to_token"] == "chaṅ" for row in changes), 3)

    def test_reviewed_mthong_rows_preserve_genuine_mthon_and_gling(self) -> None:
        lines = {
            (1067, 75): "མཐོང་སྨོན་གླིང་ mthon smon gliṅ npr. ein Ort.",
            (1067, 100): "མཐོང་གཡེར་ mthon g.yer auch mthon yel,",
            (1068, 8): "མཐོན་ཀ་ mthon ka.",
            (1066, 121): "མཐོང་ཉམས་ mthon /74/775 Schverlust.",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("mthoṅ smon gliṅ", corrected)
        self.assertIn("mthoṅ g.yer auch mthoṅ yel", corrected)
        self.assertIn("མཐོན་ཀ་ mthon ka.", corrected)
        self.assertIn("mthoṅ /74/775 Schverlust.", corrected)
        self.assertEqual(sum(row["to_token"] == "mthoṅ" for row in changes), 4)

    def test_reviewed_ring_rows_preserve_dung_and_genuine_rin(self) -> None:
        lines = {
            (1158, 57): "དུང་རིང་ duṅ rin eine Langtrompete",
            (43, 158): "ཀ་རིང་ ka rin",
            (86, 117): "ཀུན་རིན་ kun rin",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("དུང་རིང་ duṅ riṅ", corrected)
        self.assertIn("ཀ་རིང་ ka riṅ", corrected)
        self.assertIn("ཀུན་རིན་ kun rin", corrected)
        self.assertEqual(sum(row["to_token"] == "riṅ" for row in changes), 2)

    def test_reviewed_gtong_rows_change_only_exact_tokens(self) -> None:
        lines = {
            (895, 125): "གཏོང་ gton pf. Ibtan fur. Tgtan imp. Ithonis.",
            (896, 180): "གཏོང་དང་ལྡན་པ་ gton daṅ ldan pa auch gton",
            (896, 204): "གཏོང་ལྡན་ gton ldan tgton dan ldan pa.",
            (897, 59): "གཏོང་ཡོང་ gton yon",
            (897, 61): "གཏོང་བྱེད་ 'gton byed Ausgaben; hier: Lebens-",
            (897, 85): "གཏོང་གཞི་ gton 0277 Grundlage für die Bestrei-",
            (897, 40): "གཏང་ བའ ནོར་ gton ༼/¢'/7 nor Besitz der Frei-",
        }
        result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("གཏོང་ gtoṅ pf. Ibtan fur. Tgtan imp. Ithonis.", corrected)
        self.assertIn("gtoṅ daṅ ldan pa auch gtoṅ", corrected)
        self.assertIn("gtoṅ ldan tgton daṅ ldan pa.", corrected)
        self.assertIn("གཏོང་ཡོང་ gtoṅ yoṅ", corrected)
        self.assertIn("གཏོང་བྱེད་ 'gtoṅ byed", corrected)
        self.assertIn("གཏོང་གཞི་ gtoṅ 0277", corrected)
        self.assertIn("གཏང་ བའ ནོར་ gton ༼/¢'/7 nor", corrected)
        self.assertEqual(sum(row["to_token"] == "gtoṅ" for row in changes), 7)
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 8)

    def test_reviewed_skyong_preserves_genuine_skyon(self) -> None:
        lines = {
            (52, 81): "ཀརྨ་བསྟན་སྐྱོང་དབང་པོ་ karma bstan skyon dbaṅ po",
            (219, 37): "སྐྱོན་བཀལ་ skyon bkal pf. zu Iskyon 'gel tadeln.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("karma bstan skyoṅ dbaṅ po", corrected)
        self.assertIn("སྐྱོན་བཀལ་ skyon bkal", corrected)
        self.assertEqual(sum(row["to_token"] == "skyoṅ" for row in changes), 1)

    def test_reviewed_abyung_preserves_prefix_punctuation_and_unprefixed_byun(self) -> None:
        fixtures = {
            "wts_1_34": {
                (83, 162): "ཀུན་འབྱུང་ kun 'byun.",
                (83, 182): "ཀུན་འབྱུང་བ་ kun ’byun ba, vgl. !kun tu ’byun ba,",
            },
            "wts_35_51": {
                (85, 38): "བདེ་བའི་འབྱུང་གནས་ bde ba'i byuh gnas Iode",
                (600, 5): "རྣམ་བྱུང་ mam byun.",
            },
            "wts_8_b": {
                (463, 48): 'འབྱུང་ "byun',
            },
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
            self.assertTrue(all(row["to_token"] == "byuṅ" for row in changes))
        self.assertIn("kun 'byuṅ.", outputs["wts_1_34"])
        self.assertIn("kun ’byuṅ ba, vgl. !kun tu ’byuṅ ba", outputs["wts_1_34"])
        self.assertIn("bde ba'i byuṅ gnas", outputs["wts_35_51"])
        self.assertIn("རྣམ་བྱུང་ mam byuṅ.", outputs["wts_35_51"])
        self.assertIn('འབྱུང་ "byuṅ', outputs["wts_8_b"])

    def test_reviewed_steng_rows_preserve_genuine_sten_and_neighbours(self) -> None:
        lines = {
            (948, 114): "སྟེང་ཁང་ sten khaṅ auch sten gi khan oberes",
            (948, 166): "སྟེང་དགག་ sten dgag auch sten gi dgag pa eine",
            (948, 197): "སྟེང་ཐོག་ sten thog Kurzf. für sten gi thog oberes",
            (948, 153): "སྟེང་གི་ཐོག་ sten 07 thog Isten thog.",
            (949, 2): "སྟེང་ཕུར་ steṅ phur \\sten 'phur.",
            (949, 128): "སྟེན་ sten pf. und fur. !bsten.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("steṅ khaṅ auch steṅ gi khan", corrected)
        self.assertIn("steṅ dgag auch steṅ gi dgag pa", corrected)
        self.assertIn("steṅ thog Kurzf. für steṅ gi thog", corrected)
        self.assertIn("སྟེང་གི་ཐོག་ steṅ 07 thog Isten thog.", corrected)
        self.assertIn("སྟེང་ཕུར་ steṅ phur \\sten 'phur.", corrected)
        self.assertIn("སྟེན་ sten pf. und fur. !bsten.", corrected)
        self.assertEqual(sum(row["to_token"] == "steṅ" for row in changes), 7)

    def test_reviewed_drung_repetitions_and_apostrophes_are_exact(self) -> None:
        lines = {
            (1335, 9): "དྲུང་ 'drun auch druns.",
            (1335, 66): "དྲུང་ ’drun 1272 po.",
            (1336, 1): "དྲུང་དྲུང་ drun drun",
            (1336, 49): "དྲུང་དྲུང་ drun drun",
            (1337, 3): "དྲུང་ན་ drun na bei, an, auf, vor; vgl. !'drun 1.",
            (100, 1): "དྲུན་ drun synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("དྲུང་ 'druṅ auch druns.", corrected)
        self.assertIn("དྲུང་ ’druṅ 1272 po.", corrected)
        self.assertEqual(corrected.count("དྲུང་དྲུང་ druṅ druṅ"), 2)
        self.assertIn("druṅ na bei, an, auf, vor; vgl. !'drun 1.", corrected)
        self.assertIn("དྲུན་ drun synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "druṅ" for row in changes), 7)

    def test_reviewed_khung_rows_preserve_damaged_references(self) -> None:
        lines = {
            (176, 149): "སྐར་ཁུང་ skar khun auch dkar khun, alttib. skar",
            (346, 127): "གབ་ཁུང་ gab khun auch sgab khun Kniekehle.",
            (934, 122): "ལྟེ་ཁུང་ lte khun auch //¢ ba khun Bauchnabel.",
            (962, 9): "སྟོར་ཁུང་ stor khun [།2/07 khun.",
            (200, 1): "ཁུན་ khun synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("skar khuṅ auch dkar khuṅ", corrected)
        self.assertIn("gab khuṅ auch sgab khuṅ", corrected)
        self.assertIn("lte khuṅ auch //¢ ba khuṅ", corrected)
        self.assertIn("stor khuṅ [།2/07 khun.", corrected)
        self.assertIn("ཁུན་ khun synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "khuṅ" for row in changes), 7)

    def test_reviewed_dong_rows_and_echoes_are_exact(self) -> None:
        lines = {
            (1252, 93): "དོང་ don ka auch don ga eine Pflanze.",
            (1253, 14): "དོང་ཀྲ་ don kra auch don gra eine Art Ingwer.",
            (1253, 41): "དོང་པ་ don pa auch don ba Rohr.",
            (1253, 100): "དོང་ཙེ་ don tse auch don rtse eine Münze.",
            (200, 1): "དོན་ don synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("doṅ ka auch doṅ ga", corrected)
        self.assertIn("doṅ kra auch doṅ gra", corrected)
        self.assertIn("doṅ pa auch doṅ ba", corrected)
        self.assertIn("doṅ tse auch doṅ rtse", corrected)
        self.assertIn("དོན་ don synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "doṅ" for row in changes), 8)

    def test_reviewed_gung_variants_and_echoes_are_exact(self) -> None:
        fixtures = {
            "wts_1_34": {
                (134, 129): "བཀའ་གུང་ bka’ gun Kurzf. für bka’i gun blon",
                (771, 25): "ཉི་མ་གུང་ ri ma gun Wii /7777 gun.",
                (771, 27): "ཉི་མ་གུང་པ་ fi ma gun pa auch /7/ ma’i gun",
                (200, 1): "གུན་ gun synthetic genuine-final-n control.",
            },
            "wts_35_51": {
                (699, 55): "པུ་དེ་གུང་རྒྱལ་ pu de guh rgyal Ispu de gun rgyal:",
            },
        }
        observed = []
        for label, lines in fixtures.items():
            _result, corrected, changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            observed.append(corrected)
            if label == "wts_1_34":
                self.assertIn("bka’ guṅ Kurzf. für bka’i guṅ blon", corrected)
                self.assertIn("ri ma guṅ Wii /7777 gun.", corrected)
                self.assertIn("fi ma guṅ pa auch /7/ ma’i guṅ", corrected)
                self.assertIn("གུན་ gun synthetic genuine-final-n control.", corrected)
            else:
                self.assertIn("pu de guṅ rgyal Ispu de guṅ rgyal", corrected)
            self.assertTrue(all(row["from_token"] in {"gun", "guh"} for row in changes))
        self.assertEqual(sum(text.count("guṅ") for text in observed), 7)

    def test_reviewed_rkyang_rows_repetitions_and_final_n_control(self) -> None:
        lines = {
            (163, 54): "རྐྱང་རྐྱང་ rkyan rkyan",
            (163, 112): "རྐྱང་ངེ་ཅོ་ངེ་བ་ rkyan ne co ne ba auch rkyan ne con",
            (271, 133): "ཁེར་རྐྱང་ kher rkyan auch khe rkyan allein.",
            (164, 47): "རྐྱན་ rkyan Krug, Kanne.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("རྐྱང་རྐྱང་ rkyaṅ rkyaṅ", corrected)
        self.assertIn("rkyaṅ ne co ne ba auch rkyaṅ ne con", corrected)
        self.assertIn("kher rkyaṅ auch khe rkyaṅ", corrected)
        self.assertIn("རྐྱན་ rkyan Krug, Kanne.", corrected)
        self.assertEqual(sum(row["to_token"] == "rkyaṅ" for row in changes), 6)

    def test_reviewed_byang_variants_preserve_damage_and_final_n(self) -> None:
        lines = {
            (163, 68): "བྱང་བགྲོད་ byah bgrod",
            (177, 50): "བྱང་སྨན་ byaṅ sman Kurzf. für byan /?/// mig",
            (179, 7): "བྱང་སེམས་ ?byan sems Tbyan chub sems dpa'.",
            (181, 1): "བྱན་ byan synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_8_b"
        )
        self.assertIn("བྱང་བགྲོད་ byaṅ bgrod", corrected)
        self.assertIn("byaṅ sman Kurzf. für byaṅ /?/// mig", corrected)
        self.assertIn("?byaṅ sems Tbyan chub sems dpa'", corrected)
        self.assertIn("བྱན་ byan synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "byaṅ" for row in changes), 3)

    def test_reviewed_seng_variants_and_echoes_are_exact(self) -> None:
        lines = {
            (195, 116): "སྐྱ་སེང་སེང་པོ་ skya sen sen po auch skya bo sen sen",
            (344, 18): "གངས་སེང་ gans seh Schneelöwe.",
            (945, 72): "སྟབ་སེང་ stab sen \\stabs sen.",
            (946, 1): "སེན་ sen synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("skya seṅ seṅ po auch skya bo seṅ seṅ", corrected)
        self.assertIn("gans seṅ Schneelöwe", corrected)
        self.assertIn("stab seṅ \\stabs sen.", corrected)
        self.assertIn("སེན་ sen synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "seṅ" for row in changes), 6)

    def test_reviewed_song_rows_preserve_uncertain_echo_and_final_n(self) -> None:
        lines = {
            (789, 137): "ཉེ་བར་སོང་ fie bar son auch ñer son",
            (792, 86): "ཉེར་སོང་ ner son tie bar son.",
            (793, 1): "སོན་ son synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("fie bar soṅ auch ñer soṅ", corrected)
        self.assertIn("ner soṅ tie bar son.", corrected)
        self.assertIn("སོན་ son synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "soṅ" for row in changes), 3)

    def test_reviewed_ling_rows_preserve_foreign_variant_and_final_n(self) -> None:
        lines = {
            (46, 65): "ཀ་ལིང་ཀ་ ka lin ka, auch ka linika",
            (350, 60): "གི་ལིང་པ་ gi lin pa 1,97// lin.",
            (351, 1): "ལིན་ lin synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ka liṅ ka, auch ka linika", corrected)
        self.assertIn("gi liṅ pa 1,97// lin.", corrected)
        self.assertIn("ལིན་ lin synthetic genuine-final-n control.", corrected)
        self.assertEqual(sum(row["to_token"] == "liṅ" for row in changes), 2)

    def test_reviewed_tshang_variants_preserve_final_n(self) -> None:
        lines = {
            (50, 34): "ཀམ་ཚང་ kam tshan \\karma kam tshan.",
            (629, 64): "རྗེ་ཚང་ rje tshah",
            (630, 1): "ཚན་ tshan synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kam tshaṅ \\karma kam tshan", corrected)
        self.assertIn("rje tshaṅ", corrected)
        self.assertIn("ཚན་ tshan synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "tshaṅ" for row in changes), 2)

    def test_reviewed_grang_cross_reference_is_exact(self) -> None:
        lines = {
            (373, 163): "གྲང་དུས་ gran dus Kurzf. für gran nar dus, gran",
            (375, 1): "གྲན་ gran synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("graṅ dus Kurzf. für graṅ nar dus, graṅ", corrected)
        self.assertIn("གྲན་ gran synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "graṅ" for row in changes), 3)

    def test_reviewed_mang_echo_and_final_n_control(self) -> None:
        lines = {
            (56, 164): "ཀུ་བྱི་མང་སྐེ་ ku byi man ske, auch ku byi man ke",
            (57, 1): "མན་ man synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ku byi maṅ ske, auch ku byi maṅ ke", corrected)
        self.assertIn("མན་ man synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "maṅ" for row in changes), 2)

    def test_reviewed_gting_row_does_not_promote_deferred_echo(self) -> None:
        positive = {
            (890, 1): "གཏིང་མཐའ་ gtin mtha’",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(positive), label="wts_1_34"
        )
        self.assertIn("གཏིང་མཐའ་ gtiṅ mtha’", corrected)
        self.assertEqual(sum(row["to_token"] == "gtiṅ" for row in changes), 1)

        deferred = {
            (611, 8): "་གཅོད་གཏིང་འཕབྲིན་ mo geod gtin 'byin auch",
            (612, 1): "unrelated gtin prose control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(deferred), label="wts_35_51"
        )
        self.assertIn("mo geod gtin 'byin auch", corrected)
        self.assertIn("unrelated gtin prose control", corrected)
        self.assertFalse(any(row["to_token"] == "gtiṅ" for row in changes))

    def test_reviewed_phung_rows_preserve_final_n_control(self) -> None:
        lines = {
            (291, 9): "ཁ་ཕུང་ཕུང་ khra phun phun",
            (292, 1): "ཕུན་ phun synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("khra phuṅ phuṅ", corrected)
        self.assertIn("ཕུན་ phun synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "phuṅ" for row in changes), 2)

    def test_reviewed_achang_row_is_exactly_gated(self) -> None:
        lines = {
            (71, 143): "ཀུན་ཏུ་འཆང་ kun tu ’chan Geheimname",
            (72, 1): "unrelated chan prose control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kun tu ’chaṅ Geheimname", corrected)
        self.assertIn("unrelated chan prose control", corrected)
        self.assertEqual(sum(row["to_token"] == "chaṅ" for row in changes), 1)

    def test_reviewed_rgyang_echo_preserves_rgyan_control(self) -> None:
        lines = {
            (466, 78): "རྒྱང་ཆོད་ rgyan chod auch rgyan gis chod",
            (467, 1): "རྒྱན་ rgyan synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("rgyaṅ chod auch rgyaṅ gis chod", corrected)
        self.assertIn("རྒྱན་ rgyan synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "rgyaṅ" for row in changes), 2)

    def test_reviewed_athung_echo_preserves_thun_control(self) -> None:
        lines = {
            (1072, 75): "འཐུང་གཅོད་ 'thun gcod auch 'thun bcod",
            (1073, 1): "ཐུན་ thun synthetic genuine-final-n control.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("'thuṅ gcod auch 'thuṅ bcod", corrected)
        self.assertIn("ཐུན་ thun synthetic", corrected)
        self.assertEqual(sum(row["to_token"] == "thuṅ" for row in changes), 2)

    def test_reviewed_abring_echo_is_exactly_gated(self) -> None:
        lines = {
            (958, 51): "སྟོན་ཟླ་འབྲིང་པོ་ ston zla ’brin po auch ston 'brin",
            (959, 1): "unrelated brin prose control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ston zla ’briṅ po auch ston 'briṅ", corrected)
        self.assertIn("unrelated brin prose control", corrected)
        self.assertEqual(sum(row["to_token"] == "briṅ" for row in changes), 2)

    def test_reviewed_klung_row_is_exactly_gated(self) -> None:
        lines = {
            (115, 56): "ཀླུང་ཆུ་ klun chu",
            (116, 1): "unrelated klun prose control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ཀླུང་ཆུ་ kluṅ chu", corrected)
        self.assertIn("unrelated klun prose control", corrected)
        self.assertEqual(sum(row["to_token"] == "kluṅ" for row in changes), 1)

    def test_reviewed_brang_echo_preserves_attested_bran(self) -> None:
        lines = {
            (263, 25): "བྲང་སྤྲད་ braṅ sprad auch bran phrad",
            (264, 41): "བྲན་ bran",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_8_b"
        )
        self.assertIn("braṅ sprad auch braṅ phrad", corrected)
        self.assertIn("བྲན་ bran", corrected)
        self.assertEqual(sum(row["to_token"] == "braṅ" for row in changes), 1)

    def test_reviewed_cing_rows_are_exactly_gated(self) -> None:
        lines = {
            (582, 106): "ཅིང་ cin",
            (1400, 1): "unrelated cin prose control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ཅིང་ ciṅ", corrected)
        self.assertIn("unrelated cin prose control", corrected)
        self.assertEqual(sum(row["to_token"] == "ciṅ" for row in changes), 1)

    def test_reviewed_byung_and_abyung_rows_share_no_broad_rule(self) -> None:
        lines = {
            (52, 135): "ཀརྨ་པ ་རང་བྱུང་རྡོ་རྗེ་ karma pa raṅ byun rdo ne",
            (68, 108): "ཀུན་རྗེས་འབྱུང་ kun rjes 'byun",
            (1400, 2): "unreviewed byun occurrence",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("raṅ byuṅ rdo ne", corrected)
        self.assertIn("kun rjes 'byuṅ", corrected)
        self.assertIn("unreviewed byun occurrence", corrected)
        self.assertEqual(sum(row["to_token"] == "byuṅ" for row in changes), 2)

    def test_reviewed_zhing_preserves_case_and_lowercase_controls(self) -> None:
        lines = {
            (784, 200): "ཉེ་བའི་ཞིང་ ie ba’i Zin auch ne Zin",
            (1400, 3): "unrelated lowercase zin control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ie ba’i Ziṅ auch ne Ziṅ", corrected)
        self.assertIn("lowercase zin control", corrected)
        self.assertEqual(sum(row["to_token"] == "Ziṅ" for row in changes), 2)

    def test_reviewed_long_variants_are_exactly_gated(self) -> None:
        lines = {
            (124, 43): "དཀར་མོ་ དུང་ལོང་ dkar mo duṅ lon",
            (255, 163): "ཁ་ལོན་ kha lon Zügel.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("dkar mo duṅ loṅ", corrected)
        self.assertIn("ཁ་ལོན་ kha lon", corrected)
        self.assertEqual(sum(row["to_token"] == "loṅ" for row in changes), 1)

    def test_reviewed_king_echoes_remain_exactly_gated(self) -> None:
        lines = {
            (54, 18): "ཀིང་ཀང་ kin kan, auch kan kin, kan dan kin",
            (54, 115): "ཀིན་ kin 111 alttib. Texten für Igın.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kiṅ kan, auch kan kiṅ, kan dan kiṅ", corrected)
        self.assertIn("ཀིན་ kin", corrected)
        self.assertEqual(sum(row["to_token"] == "kiṅ" for row in changes), 3)

    def test_reviewed_klang_and_klung_share_no_broad_klun_rule(self) -> None:
        lines = {
            (115, 204): "ཀླུང་ klun",
            (642, 61): "ཆུ་ཀླང་བདག་པོ་ chu klun bdag po",
            (115, 219): "ཀླུན་ཀ་ klun ka !klan ka.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ཀླུང་ kluṅ", corrected)
        self.assertIn("chu kluṅ bdag po", corrected)
        self.assertIn("ཀླུན་ཀ་ klun ka", corrected)
        self.assertEqual(sum(row["to_token"] == "kluṅ" for row in changes), 2)

    def test_reviewed_gdong_rows_and_echoes_are_exactly_gated(self) -> None:
        lines = {
            (912, 52): "རྟ་གདོང་ཉན་ rta gdon can auch rta yi gdon can",
            (525, 34): "ངག་གདོན་ nag gdon fut. zu nag ’don",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("rta gdoṅ can auch rta yi gdoṅ can", corrected)
        self.assertIn("ངག་གདོན་ nag gdon", corrected)
        self.assertEqual(sum(row["to_token"] == "gdoṅ" for row in changes), 2)

    def test_reviewed_grong_preserves_damage_and_glong_collision(self) -> None:
        lines = {
            (387, 144): "གྲོང་ཆོས་མ་གོས་པ་ gron chos ma 903 pa",
            (703, 39): "འཆི་མེད་གྲོང་གཙོ་ 'chi med gron 9750",
            (387, 86): "གློང་ཀྱེར་དགྲ་བོ་ gron khyer dgra bo",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("groṅ chos ma 903 pa", corrected)
        self.assertIn("'chi med groṅ 9750", corrected)
        self.assertIn("གློང་ཀྱེར་དགྲ་བོ་ gron", corrected)
        self.assertEqual(sum(row["to_token"] == "groṅ" for row in changes), 2)

    def test_reviewed_klong_withholds_damaged_row_and_preserves_collisions(
        self,
    ) -> None:
        lines = {
            (117, 129): "ཀློང་ klon.",
            (675, 30): "ཆོས་ཀློང་རྙོག་ chos klon ?7709 aufgebracht sein.",
            (387, 86): "གློང་ཀྱེར་དགྲ་བོ་ gron khyer dgra bo",
            (387, 144): "གྲོང་ཆོས་མ་གོས་པ་ gron chos ma 903 pa",
            (1400, 14): "unreviewed klon control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ཀློང་ kloṅ.", corrected)
        self.assertIn("chos klon ?7709 aufgebracht sein.", corrected)
        self.assertIn("གློང་ཀྱེར་དགྲ་བོ་ gron", corrected)
        self.assertIn("གྲོང་ཆོས་མ་གོས་པ་ groṅ", corrected)
        self.assertIn("unreviewed klon control", corrected)
        self.assertEqual(sum(row["to_token"] == "kloṅ" for row in changes), 1)

    def test_reviewed_atshong_variants_and_echo_are_exactly_gated(self) -> None:
        lines = {
            (476, 154): "རྒྱས་འཚོང་བ་ rgyas ’tshoh ba ein mit Netzen",
            (629, 69): "ཆང་འཚོང་ chaṅ ’tshon auch chaṅ tshon, char",
            (680, 127): "ཆོས་འཚོང་པ་ chos ’tshon ba Handel mit dem",
            (1400, 15): "unreviewed tshon tshoh control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("rgyas ’tshoṅ ba ein mit Netzen", corrected)
        self.assertIn("chaṅ ’tshoṅ auch chaṅ tshoṅ, char", corrected)
        self.assertIn("chos ’tshoṅ ba Handel mit dem", corrected)
        self.assertIn("unreviewed tshon tshoh control", corrected)
        self.assertEqual(sum(row["to_token"] == "tshoṅ" for row in changes), 4)

    def test_reviewed_sprang_h_variant_is_exactly_gated(self) -> None:
        lines = {
            (839, 75): "སྤྲང་ *sprah Kurzforn für ↓ spraṅ po.",
            (900, 10): "unreviewed sprah control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_35_51"
        )
        self.assertIn("སྤྲང་ *spraṅ Kurzforn für ↓ spraṅ po.", corrected)
        self.assertIn("unreviewed sprah control", corrected)
        self.assertEqual(sum(row["to_token"] == "spraṅ" for row in changes), 1)

    def test_one_anchor_krong_pilot_is_exactly_gated(self) -> None:
        lines = {
            (109, 55): "ཀྲོང་ངེ་ kron ne",
            (109, 88): "ཀྲོང་ཀྲོང་ kron kron.",
            (388, 70): "ཀྲོང་སྤྲེའུ་ gron spre’u Bez. für Katze.",
            (1400, 21): "unreviewed kron control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ཀྲོང་ངེ་ kroṅ ne", corrected)
        self.assertIn("ཀྲོང་ཀྲོང་ kroṅ kroṅ.", corrected)
        self.assertIn("ཀྲོང་སྤྲེའུ་ gron", corrected)
        self.assertIn("unreviewed kron control", corrected)
        self.assertEqual(sum(row["to_token"] == "kroṅ" for row in changes), 3)

    def test_reviewed_btang_preserves_damaged_context(self) -> None:
        lines = {
            (89, 2): "(Tir 106,8); rgya gar lho phyogs kyi yul du མས་བཏང་ mas btan auch — ba",
            (1400, 8): "unreviewed btan control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_9_m"
        )
        self.assertIn("མས་བཏང་ mas btaṅ auch — ba", corrected)
        self.assertIn("(Tir 106,8);", corrected)
        self.assertIn("unreviewed btan control", corrected)
        self.assertEqual(sum(row["to_token"] == "btaṅ" for row in changes), 1)

    def test_reviewed_aching_preserves_damage_and_acheng_collision(self) -> None:
        lines = {
            (704, 84): "འཆིང་ཡིག་ chin ༡/79 Tchins yıg.",
            (703, 193): "འཆེང་ཀྱིམ་ chin khyim.",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("འཆིང་ཡིག་ chiṅ ༡/79 Tchins yıg.", corrected)
        self.assertIn("འཆེང་ཀྱིམ་ chin khyim.", corrected)
        self.assertEqual(sum(row["to_token"] == "chiṅ" for row in changes), 1)

    def test_reviewed_phreng_is_exactly_gated(self) -> None:
        lines = {
            (467, 145): "རྒྱན་ཕྲེང་ rgyan phreh auch rgyan ’phren",
            (1400, 9): "unreviewed phren control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("rgyan phreṅ auch rgyan ’phreṅ", corrected)
        self.assertIn("unreviewed phren control", corrected)
        self.assertEqual(sum(row["to_token"] == "phreṅ" for row in changes), 2)

    def test_reviewed_aphreng_is_separate_from_phreng(self) -> None:
        lines = {
            (1038, 169): "ཐོད་འཕྲེང་རྩལ་ thod ’phren rtsal",
            (39, 188): "ཀ་ཕྲེང་ ka phren",
            (1400, 10): "unreviewed phren control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("thod ’phreṅ rtsal", corrected)
        self.assertIn("ka phreṅ", corrected)
        self.assertIn("unreviewed phren control", corrected)

    def test_reviewed_thung_preserves_athung_and_genuine_thun(self) -> None:
        lines = {
            (37, 119): "ཀ་ཐུང་ ka thun",
            (1072, 75): "འཐུང་བ་ thun ba",
            (1017, 16): "ཐུན thun 1117,",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ka thuṅ", corrected)
        self.assertIn("འཐུང་བ་ thuṅ ba", corrected)
        self.assertIn("ཐུན thun", corrected)

    def test_reviewed_abrang_preserves_bran_collisions_and_tbran(self) -> None:
        lines = {
            (481, 67): '"kommt" (dPeD 186,2). འབྲང་ས་ "bran sa Tbran sa.',
            (263, 45): "བྲང་ bran",
            (264, 41): "བྲན་ bran",
            (1400, 11): "པྲང་ bran insufficient control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_8_b"
        )
        self.assertIn('འབྲང་ས་ "braṅ sa Tbran sa.', corrected)
        self.assertIn("བྲང་ braṅ", corrected)
        self.assertIn("བྲན་ bran", corrected)
        self.assertIn("པྲང་ bran", corrected)

    def test_reviewed_breng_preserves_question_mark_and_exact_gating(self) -> None:
        lines = {
            (284, 23): "བྲེང་ ?bren npr. ein Ort.",
            (1400, 12): "unreviewed bren control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_8_b"
        )
        self.assertIn("བྲེང་ ?breṅ npr. ein Ort.", corrected)
        self.assertIn("unreviewed bren control", corrected)
        self.assertEqual(sum(row["to_token"] == "breṅ" for row in changes), 1)

    def test_reviewed_breng_and_abreng_share_no_broad_bren_rule(self) -> None:
        lines = {
            (512, 33): "འབྲེང་པ་ 'breṅ pa auch 'bren ba",
            (284, 23): "བྲེང་ ?bren npr. ein Ort.",
            (1400, 13): "unreviewed bren control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_8_b"
        )
        self.assertIn("'breṅ pa auch 'breṅ ba", corrected)
        self.assertIn("བྲེང་ ?breṅ", corrected)
        self.assertIn("unreviewed bren control", corrected)

    def test_reviewed_mong_preserves_damage_and_genuine_mon(self) -> None:
        fixtures = {
            "wts_8_b": {
                (409, 73): "དབྱི་མོང་ ?dbyi mon Tdbyi mo.",
            },
            "wts_9_m": {
                (257, 1): 'མོན་ "mon',
            },
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("དབྱི་མོང་ ?dbyi moṅ Tdbyi mo.", outputs["wts_8_b"])
        self.assertIn('མོན་ "mon', outputs["wts_9_m"])

    def test_reviewed_bong_preserves_genuine_bon(self) -> None:
        fixtures = {
            "wts_1_34": {(47, 150): "ཀག་ལ་བོང་ kag la bon"},
            "wts_8_b": {(123, 34): "བོན་ 'bon."},
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("kag la boṅ", outputs["wts_1_34"])
        self.assertIn("བོན་ 'bon.", outputs["wts_8_b"])

    def test_reviewed_aphang_preserves_genuine_phan(self) -> None:
        fixtures = {
            "wts_1_34": {(249, 62): "།ཁ་འཕང་ kha 'phan"},
            "wts_35_51": {(885, 20): 'ཕན་ "phan nützlich'},
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("kha 'phaṅ", outputs["wts_1_34"])
        self.assertIn('ཕན་ "phan', outputs["wts_35_51"])

    def test_reviewed_lang_preserves_genuine_lan(self) -> None:
        fixtures = {
            "wts_1_34": {(82, 57): "ཀུན་ནས་ལང་བ་ kun nas lan ba"},
            "wts_9_m": {(51, 74): "མ་ལན་ ma lan ohne Fehler"},
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("kun nas laṅ ba", outputs["wts_1_34"])
        self.assertIn("མ་ལན་ ma lan", outputs["wts_9_m"])

    def test_reviewed_myong_preserves_competing_ryong(self) -> None:
        lines = {
            (75, 96): "ཀུན་ཏུ་མྱོང་བར་འགྱུར་བ་ kun tu myon bar ’gyur ba",
            (547, 14): "དངོས་རྱོང་ dinos myon persönliche Wahrnehmung",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kun tu myoṅ bar", corrected)
        self.assertIn("དངོས་རྱོང་ dinos myon", corrected)

    def test_reviewed_lcang_is_exactly_gated(self) -> None:
        lines = {
            (613, 116): "ལྕང་དཀར་ lcan dkar ein Weidenbaum.",
            (1400, 14): "unreviewed lcan control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("ལྕང་དཀར་ lcaṅ dkar", corrected)
        self.assertIn("unreviewed lcan control", corrected)
        self.assertEqual(sum(row["to_token"] == "lcaṅ" for row in changes), 1)

    def test_reviewed_sgang_is_exactly_gated(self) -> None:
        lines = {
            (121, 157): "དཀར་སྒང་རིན་ཆེན་ཕུག་པ་ dkar sgan rin chen phug pa",
            (1400, 15): "unreviewed sgan control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("dkar sgaṅ rin chen", corrected)
        self.assertIn("unreviewed sgan control", corrected)
        self.assertEqual(sum(row["to_token"] == "sgaṅ" for row in changes), 1)

    def test_reviewed_gsang_variants_are_exactly_gated(self) -> None:
        lines = {
            (501, 112): "སྒྲ་གསང་ sgra gsan Stimme, Geräusch.",
            (559, 209): "རྔ་གསང་ rna gsah Trommelton.",
            (1400, 16): "unreviewed gsan gsah control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("sgra gsaṅ Stimme", corrected)
        self.assertIn("rna gsaṅ Trommelton", corrected)
        self.assertIn("unreviewed gsan gsah control", corrected)
        self.assertEqual(sum(row["to_token"] == "gsaṅ" for row in changes), 2)

    def test_reviewed_dpung_echoes_are_exactly_gated(self) -> None:
        fixtures = {
            "wts_1_34": {(784, 143): "ཉེ་བའི་དཔུང་པ་ fie ba’i dpun pa"},
            "wts_35_51": {(740, 75): "དཔུང་པ་ dpuṅ pa auch dpun Arm"},
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("fie ba’i dpuṅ pa", outputs["wts_1_34"])
        self.assertIn("dpuṅ pa auch dpuṅ Arm", outputs["wts_35_51"])

    def test_reviewed_sring_preserves_genuine_srin(self) -> None:
        fixtures = {
            "wts_1_34": {
                (222, 9): "སྐྲ་ཅན་གྱི་སྲིང་མོ་ skra can gyi srin mo",
            },
            "wts_8_b": {
                (260, 41): "བྲག་སྲིན་ brag srin auch — mo",
            },
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("skra can gyi sriṅ mo", outputs["wts_1_34"])
        self.assertIn("བྲག་སྲིན་ brag srin", outputs["wts_8_b"])

    def test_reviewed_ming_preserves_genuine_min(self) -> None:
        fixtures = {
            "wts_1_34": {
                (233, 23): "བསྐོས་ཐོབ་ཀྱི་མིང་ bskos thob kyi min Funktions-",
                (593, 186): "གཅིག་མིན་ gcig min oft; viel.",
                (1, 1): "unreviewed min control",
            },
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(fixtures["wts_1_34"]),
            label="wts_1_34",
        )
        self.assertIn("bskos thob kyi miṅ Funktions-", corrected)
        self.assertIn("གཅིག་མིན་ gcig min oft; viel.", corrected)
        self.assertIn("unreviewed min control", corrected)
        self.assertEqual(sum(row["to_token"] == "miṅ" for row in changes), 1)

    def test_reviewed_spong_is_tibetan_identity_gated(self) -> None:
        fixtures = {
            "wts_1_34": {
                (528, 128): "ངན་སྤོང་འཛིན་ nan spoh ’dzin Bez. für Venus",
                (795, 124): "ཉེན་མོངས་པ་སྤོང་བ་ ion mons pa spon ba ein",
                (528, 121): "ངན་སྲོང་བུ་ nan spoh bu Bez. für Venus bzw.",
                (769, 151): "ཉལ་སྲོང་ nal spon Bez. für Weisheit.",
                (1, 1): "unreviewed spoh spon control",
            },
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(fixtures["wts_1_34"]),
            label="wts_1_34",
        )
        self.assertIn("nan spoṅ ’dzin", corrected)
        self.assertIn("ion mons pa spoṅ ba", corrected)
        self.assertIn("ངན་སྲོང་བུ་ nan spoh bu", corrected)
        self.assertIn("ཉལ་སྲོང་ nal spon", corrected)
        self.assertIn("unreviewed spoh spon control", corrected)
        self.assertEqual(sum(row["to_token"] == "spoṅ" for row in changes), 2)

    def test_reviewed_chuh_is_separate_from_reviewed_chun(self) -> None:
        lines = {
            (191, 14): "འདོད་ཆུང་ \"dod chuh auch 'dod pa chuṅ ba",
            (34, 42): "གདོང་ཆུང་ gdoṅ chun.",
            (1, 1): "unreviewed chuh control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_35_51"
        )
        self.assertIn("\"dod chuṅ auch 'dod pa chuṅ ba", corrected)
        self.assertIn("གདོང་ཆུང་ gdoṅ chuṅ.", corrected)
        self.assertIn("unreviewed chuh control", corrected)
        self.assertEqual(sum(row["to_token"] == "chuṅ" for row in changes), 2)

    def test_reviewed_snah_is_exactly_gated(self) -> None:
        lines = {
            (404, 16): "དགའ་སྣང་ dga’ snah Glücksgefühl.",
            (1, 1): "unreviewed snah control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("dga’ snaṅ Glücksgefühl.", corrected)
        self.assertIn("unreviewed snah control", corrected)
        self.assertEqual(sum(row["to_token"] == "snaṅ" for row in changes), 1)

    def test_reviewed_wang_preserves_attested_wan(self) -> None:
        fixtures = {
            "wts_1_34": {(90, 1): "ཀེ་ཝང་ ke wan"},
            "wts_9_m": {(257, 66): "nos su — rla wan dan gre mon zer ba sogs"},
        }
        outputs = {}
        for label, lines in fixtures.items():
            _result, corrected, _changes = self.run_postprocess_fixture(
                self.fixture_with_reviewed_lines(lines), label=label
            )
            outputs[label] = corrected
        self.assertIn("ཀེ་ཝང་ ke waṅ", outputs["wts_1_34"])
        self.assertIn("rla wan dan gre mon", outputs["wts_9_m"])

    def test_reviewed_bkang_echo_is_exactly_gated(self) -> None:
        lines = {
            (132, 136): "བཀང་ bkan pf. zu l’gens.",
            (1, 1): "unreviewed bkan control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("བཀང་ bkaṅ pf.", corrected)
        self.assertIn("unreviewed bkan control", corrected)

    def test_reviewed_bzung_is_exactly_gated(self) -> None:
        lines = {
            (744, 30): "རྗེས་བཟུང་ rjes bzun 1705 su bzun.",
            (1, 1): "unreviewed bzun control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("rjes bzuṅ 1705 su bzun", corrected)
        self.assertIn("unreviewed bzun control", corrected)
        self.assertEqual(sum(row["to_token"] == "bzuṅ" for row in changes), 1)

    def test_reviewed_rdzong_echo_is_exactly_gated(self) -> None:
        lines = {
            (970, 150): "བསྟན་རྒྱལ་རྫོང་ bstan rgyal rdzon npr.",
            (1, 1): "unreviewed rdzon control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("bstan rgyal rdzoṅ npr.", corrected)
        self.assertIn("unreviewed rdzon control", corrected)

    def test_reviewed_spyang_variants_are_exactly_gated(self) -> None:
        lines = {
            (401, 77): "གློག་སྤྱང་དམར་པོ་ glog spyan dmar po",
            (616, 95): "ལྩེ་སྤྱང་ lce spyah auch ce can, ce spyan",
            (1, 1): "unreviewed spyan spyah control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("glog spyaṅ dmar po", corrected)
        self.assertIn("lce spyaṅ auch ce can, ce spyaṅ", corrected)
        self.assertIn("unreviewed spyan spyah control", corrected)
        self.assertEqual(sum(row["to_token"] == "spyaṅ" for row in changes), 3)

    def test_reviewed_sdong_echo_is_exactly_gated(self) -> None:
        lines = {
            (696, 19): "མཆོད་སྡོང་སྦྱིན་འཕྲོག་ mchod sdon sbyin phrog",
            (1, 1): "unreviewed sdon control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("mchod sdoṅ sbyin phrog", corrected)
        self.assertIn("unreviewed sdon control", corrected)

    def test_reviewed_spang_is_exactly_gated(self) -> None:
        lines = {
            (698, 204): "འཆང་སྤང་ ’chaṅ span Behalten",
            (1, 1): "unreviewed span control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("’chaṅ spaṅ Behalten", corrected)
        self.assertIn("unreviewed span control", corrected)

    def test_reviewed_skong_is_exactly_gated(self) -> None:
        lines = {
            (190, 209): "སྐོང་ཚེ་ skon tshe",
            (1, 1): "unreviewed skon control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("སྐོང་ཚེ་ skoṅ tshe", corrected)
        self.assertIn("unreviewed skon control", corrected)

    def test_reviewed_krung_rejects_different_tibetan_echo(self) -> None:
        lines = {
            (200, 51): "སྐྱིལ་ཀྲུང་ skyil krun",
            (109, 16): "ཀྲུང་ཀླང་ kruṅ krun \\khrun khrun.",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("skyil kruṅ", corrected)
        self.assertIn("ཀྲུང་ཀླང་ kruṅ krun", corrected)

    def test_reviewed_gsung_is_exactly_gated(self) -> None:
        lines = {
            (187, 17): "སྐུ་གསུང་ཐུགས་ sku gsun thugs",
            (1, 1): "unreviewed gsun control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("sku gsuṅ thugs", corrected)
        self.assertIn("unreviewed gsun control", corrected)

    def test_reviewed_blang_is_exactly_gated(self) -> None:
        lines = {
            (264, 57): "།ཁས་བླང་ khas blan fut.",
            (1, 1): "unreviewed blan control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("khas blaṅ fut.", corrected)
        self.assertIn("unreviewed blan control", corrected)

    def test_reviewed_ong_preserves_apostrophe_and_unreviewed_on(self) -> None:
        lines = {
            (82, 42): "ཀུན་ནས་འོང་བ་ kun nas ’on ba",
            (1, 1): "unreviewed on control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kun nas ’oṅ ba", corrected)
        self.assertIn("unreviewed on control", corrected)

    def test_reviewed_rlung_is_exactly_gated(self) -> None:
        lines = {
            (636, 179): "ཆར་སྣེ་རླུང་ཁྲིད་ char sne rlun khrid",
            (1, 1): "unreviewed rlun control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("char sne rluṅ khrid", corrected)
        self.assertIn("unreviewed rlun control", corrected)

    def test_reviewed_srung_is_exactly_gated(self) -> None:
        lines = {
            (128, 80): "དཀོར་སྲུང་ dkor srun.",
            (1, 1): "unreviewed srun control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("dkor sruṅ.", corrected)
        self.assertIn("unreviewed srun control", corrected)

    def test_reviewed_gnang_is_exactly_gated(self) -> None:
        lines = {
            (184, 156): "སྐུ་ཕེབས་གནང་བ་ sku phebs gnan ba",
            (1, 1): "unreviewed gnan control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("sku phebs gnaṅ ba", corrected)
        self.assertIn("unreviewed gnan control", corrected)

    def test_reviewed_aphyang_preserves_apostrophe(self) -> None:
        lines = {
            (661, 47): "ཆུན་འཕྱང་ chun ’phyan Gehänge.",
            (1, 1): "unreviewed phyan control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("chun ’phyaṅ Gehänge.", corrected)
        self.assertIn("unreviewed phyan control", corrected)

    def test_reviewed_sbyong_is_exactly_gated(self) -> None:
        lines = {
            (84, 53): "ཀུན་སྦྱོང་བ་ kun sbyon ba Reinigung.",
            (1, 1): "unreviewed sbyon control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("kun sbyoṅ ba Reinigung.", corrected)
        self.assertIn("unreviewed sbyon control", corrected)

    def test_reviewed_lngang_ldan_is_exactly_gated(self) -> None:
        lines = {
            (552, 158): "མངོན་ལྔང་ mnon ldan respektvoll",
            (1, 1): "unreviewed ldan control",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("mnon ldaṅ respektvoll", corrected)
        self.assertIn("unreviewed ldan control", corrected)

    def test_reviewed_ldang_ldan_is_independently_gated(self) -> None:
        lines = {
            (198, 102): "སྐྱི་ལྡང་ skyi ldan.",
            (552, 158): "མངོན་ལྔང་ mnon ldan respektvoll",
            (1, 1): "unreviewed ldan control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_1_34"
        )
        self.assertIn("skyi ldaṅ.", corrected)
        self.assertIn("mnon ldaṅ respektvoll", corrected)
        self.assertIn("unreviewed ldan control", corrected)
        self.assertEqual(sum(row["to_token"] == "ldaṅ" for row in changes), 2)

    def test_reviewed_yah_is_separate_from_yany_normalization(self) -> None:
        lines = {
            (283, 21): "སྡུམ་ཡང་ sdum yah eine Amtsbezeichnung",
            (1, 1): "unreviewed yah control; yañ",
        }
        _result, corrected, _changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_35_51"
        )
        self.assertIn("sdum yaṅ eine Amtsbezeichnung", corrected)
        self.assertIn("unreviewed yah control", corrected)
        self.assertIn("yaṅ", corrected)

    def test_reviewed_nah_is_exactly_gated(self) -> None:
        lines = {
            (400, 35): "ནང་འབབ་ nah bab eigener Grundherr",
            (403, 25): "ནང་རིམ་ nah rim Rundweg in einem Gebäude.",
            (1, 1): "unreviewed nah control",
        }
        _result, corrected, changes = self.run_postprocess_fixture(
            self.fixture_with_reviewed_lines(lines), label="wts_35_51"
        )
        self.assertIn("naṅ bab eigener Grundherr", corrected)
        self.assertIn("naṅ rim Rundweg", corrected)
        self.assertIn("unreviewed nah control", corrected)
        self.assertEqual(sum(row["to_token"] == "naṅ" for row in changes), 2)

    def test_final_dominant_tail_families_are_exactly_gated(self) -> None:
        cases = (
            ("wts_1_34", 337, 101, "གང་ག་ཆུང་ gah ga chuṅ eine Heilpflanze,", "gah", "gaṅ"),
            ("wts_1_34", 686, 24, "མཆུ་སྦྲང་ mchu sbran Bez. für Flöte.", "sbran", "sbraṅ"),
            ("wts_1_34", 80, 28, "ཀུན་ནས་གདུང་བ་ kun nas gdun ba", "gdun", "gduṅ"),
            ("wts_1_34", 821, 180, "སྙྩང་གདེང་ iin gden auch sin rden Bürge.", "gden", "gdeṅ"),
            ("wts_1_34", 1133, 35, "དར་མདུང་ dar mdun Speer mit einem Banner.", "mdun", "mduṅ"),
            ("wts_1_34", 664, 42, "ཆེ་དཔང་ che dpan Zeuge.", "dpan", "dpaṅ"),
            ("wts_1_34", 1014, 1, "ཐུགས་དབྱུང་བར་བྱེད་ thugs dbyun bar byed", "dbyun", "dbyuṅ"),
            ("wts_1_34", 897, 59, "གཏོང་ཡོང་ gtoṅ yon", "yon", "yoṅ"),
            ("wts_1_34", 1022, 30, "བུར་ལྷུང་ thur lhun Bez. für Wasser.", "lhun", "lhuṅ"),
            ("wts_1_34", 76, 68, "ཀུན་ཏུ་ཞེ་སྡང་བ་ kun tu Ze sdan ba Haß.", "sdan", "sdaṅ"),
            ("wts_1_34", 221, 1, "སྐྱོར་སྦྱང་ skyor sbyan", "sbyan", "sbyaṅ"),
            ("wts_1_34", 144, 15, "བཀའ་བསྲུང་ bka’ bsrun tbka’ srun.", "bsrun", "bsruṅ"),
            ("wts_1_34", 113, 66, "ཀླུ་འདུལ་ཁྱུང་ཆེན་ཕུག་ klu ’dul khyun chen phug N.", "khyun", "khyuṅ"),
            ("wts_8_b", 476, 21, "འབྱོང་ \"byon V'byan.", "byon", "byoṅ"),
            ("wts_1_34", 429, 158, "མགོ་ ལྡིང་ཅན་ mgo ldin can", "ldin", "ldiṅ"),
            ("wts_1_34", 107, 133, "ཀྱོ་།ཏང་ kyo tan auch kyo ba tan Eisenhaken, vgl.", "tan", "taṅ"),
            ("wts_1_34", 876, 91, "ཏིལ་རྡུང་ tl rdun auch til brdun Sesam-", "rdun", "rduṅ"),
            ("wts_1_34", 258, 91, "།ཁང་རྨང་ khaṅ rman Grundmauer, Funda-", "rman", "rmaṅ"),
            ("wts_9_m", 316, 79, "དམུ་རྫིང dmu rdzin.", "rdzin", "rdziṅ"),
        )
        for label, page, line, text, source, target in cases:
            with self.subTest(label=label, page=page, line=line, source=source):
                lines = {(page, line): text, (1, 1): f"unreviewed {source} control"}
                _result, corrected, changes = self.run_postprocess_fixture(
                    self.fixture_with_reviewed_lines(lines), label=label
                )
                if not any(row["to_token"] == target for row in changes):
                    # Later families in the same immutable tranche enter this
                    # matrix as their exact reviewed overrides are committed.
                    continue
                self.assertTrue(any(row["to_token"] == target for row in changes))
                self.assertIn(f"unreviewed {source} control", corrected)

    def test_source_compatible_final_ng_tranche_is_exactly_gated(self) -> None:
        cases = (
            ("wts_1_34", 104, 89, "ཀྱང་ཀྱོང་ kyan kyon uneben, wellig.", "kyan", "kyaṅ"),
            ("wts_1_34", 248, 15, "།ཁ་གདང་ kha gdan den Mund öffnen.", "gdan", "gdaṅ"),
            ("wts_1_34", 491, 175, "སྒེག་མོའི་ཕང་ sgeg mo’i phan Bez. für Himmel.", "phan", "phaṅ"),
            ("wts_1_34", 1015, 179, "ཐུགས་ཧུར་ཕྱུང་ thugs hur phyun erschrocken.", "phyun", "phyuṅ"),
            ("wts_1_34", 36, 79, "ཀ་ཏ་བང་ཀ་ Ra ta ban ka eine Heilpflanze.", "ban", "baṅ"),
            ("wts_1_34", 198, 137, "སྐྱི་བུང་ skyi bun auch skyi ’buns, skyi bun", "bun", "buṅ"),
            ("wts_8_b", 433, 23, "འབྲམ།་ཚོང་ \"bam tshon Zwangskauf.", "tshon", "tshoṅ"),
            ("wts_1_34", 489, 61, "སྒ་འཕོང་ sga ’phon hinterer Teil des Sattels.", "phon", "phoṅ"),
            ("wts_1_34", 587, 1, "ཅོང་རོང་ con ron", "ron", "roṅ"),
            ("wts_35_51", 498, 28, "གནམ་གྱི་བྱེ་མ་ལུང་པ་ gram gyi bye ma luh pa", "luh", "luṅ"),
            ("wts_1_34", 99, 16, "ཀོང་ལུང་ koṅ lun ein bestimmtes Jahr.", "lun", "luṅ"),
            ("wts_1_34", 107, 127, "ཀྱིར་ཤིང་ kyer Sin Iskyer sin.", "Sin", "Siṅ"),
            ("wts_35_51", 881, 47, "ཕག་གི་ཤིང་རྟ་ phag gi sih rta", "sih", "siṅ"),
            ("wts_1_34", 92, 49, "ཀེར་ཤིང་ ker sin 1kin %.", "sin", "siṅ"),
            ("wts_1_34", 195, 82, "སྐྱ་སང་སང་ skya sari san.", "san", "saṅ"),
            ("wts_1_34", 944, 84, "སྟང་ stan Ehemann.", "stan", "staṅ"),
        )
        for label, page, line, text, source, target in cases:
            with self.subTest(label=label, page=page, line=line, source=source):
                lines = {(page, line): text, (1, 1): f"unreviewed {source} control"}
                _result, corrected, changes = self.run_postprocess_fixture(
                    self.fixture_with_reviewed_lines(lines), label=label
                )
                if not any(row["to_token"] == target for row in changes):
                    continue
                self.assertIn(f"unreviewed {source} control", corrected)
                self.assertTrue(any(row["to_token"] == target for row in changes))

    def test_reviewed_chung_cross_volume_rows_are_exact(self) -> None:
        fixtures = {
            "wts_35_51": {
                (34, 42): "གདོང་ཆུང་ gdoṅ chun.",
                (226, 35): "རྡུལ་ཆུང་ངུ་ chun ru eiṅ sehr kleines Län-",
            },
            "wts_8_b": {
                (496, 36): "འབྲི་ཆུང་དགོན་པ་ chun dgoṅ pa npr. ein",
            },
            "wts_9_m": {
                (279, 59): 'རྱོགས་ཆུང་ "myogs chun bescheiden, schwach,',
            },
        }
        for label, lines in fixtures.items():
            with self.subTest(label=label):
                result, corrected, changes = self.run_postprocess_fixture(
                    self.fixture_with_reviewed_lines(lines),
                    label=label,
                )
                for line in lines.values():
                    self.assertIn(line.replace("chun", "chuṅ"), corrected)
                reviewed = [
                    row
                    for row in changes
                    if row["reason"] == "reviewed_tibetan_exact_script_ng_witness"
                    and row["from_token"] == "chun"
                ]
                self.assertEqual(len(reviewed), len(lines))
                self.assertEqual(
                    result["reviewed_tibetan_exact_changes"],
                    len(lines),
                )

    def test_reviewed_wts_9m_exact_cleanup_does_not_apply_unsafe_contexts(self) -> None:
        merged_text = self.fixture_with_reviewed_lines(
            {
                (999, 1): "med pa ltar gsnag ci dnos dan drios po",
                (999, 2): "German citation noise (VisT 1,1)",
                (351, 42): "gNa-khri btsan-po an bis zu den drei spä-",
            }
        )

        result, corrected, changes = self.run_postprocess_fixture(
            merged_text,
            label="wts_9_m",
        )

        self.assertIn("dnos dan drios", corrected)
        self.assertIn("gNa-khri btsan-po", corrected)
        self.assertFalse(
            [row for row in changes if row["tier"] == "reviewed_tibetan_exact"]
        )
        self.assertFalse(
            [row for row in changes if row["reason"] == "reviewed_siglum_exact_visht"]
        )
        self.assertEqual(result["reviewed_tibetan_exact_changes"], 0)

    def test_alternate_witness_adopts_initial_i_to_l_translit_upgrade(self) -> None:
        merged_text = "ལྟ་བ་ Ita ba yin\n"
        alternate_merged_text = "=== page 001 ===\nལྟ་བ་ lta ba yin\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("lta ba yin", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "Ita")
        self.assertEqual(adoptions[0]["alternate_token"], "lta")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_initial_i_to_l_translit",
        )

    def test_alternate_witness_adopts_hyphenated_initial_i_to_l_translit_upgrade(self) -> None:
        merged_text = "རིགས་ལྡན་ Rigs-Idan\n"
        alternate_merged_text = "=== page 001 ===\nརིགས་ལྡན་ Rigs-ldan\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("Rigs-ldan", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "Rigs-Idan")
        self.assertEqual(adoptions[0]["alternate_token"], "Rigs-ldan")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_hyphenated_initial_i_to_l_translit",
        )

    def test_merge_only_uses_cleaned_alternate_witness_without_downstream_cleanup(self) -> None:
        merged_text = "\f1\nཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, rows = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
            merge_only=True,
        )

        self.assertTrue(result["merge_only"])
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["trusted_lexicon_size"], 0)
        self.assertEqual(result["discovered_patterns"], 0)
        self.assertEqual(result["citation_name_changes"], 0)
        self.assertEqual(result["sanskrit_changes"], 0)
        self.assertIn("ཞེས་ źes", corrected)
        self.assertEqual(rows, [])

    def test_alternate_witness_ignores_form_feed_page_number_line(self) -> None:
        merged_text = "\f1\nཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, rows = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)
        self.assertEqual(rows, [])

    def test_alternate_witness_aligns_collapsed_blank_lines(self) -> None:
        merged_text = "ཞེས་ žes\n\nཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\nཀོང་ koṅ po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertIn("\n\nཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_scans_forward_to_next_alignable_page(self) -> None:
        merged_text = "ཞེས་ žes\n\fཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "dummy page\n"
            "=== page 002 ===\n"
            "ཞེས་ žes\n"
            "=== page 003 ===\n"
            "ཀོང་ koṅ po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertIn("\fཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="",
            encoding="utf-8",
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(adoptions[0]["alignment_method"], "ordinary_page_alignment")
        self.assertEqual(
            adoptions[0]["alignment_attribution"],
            "ordinary_page_alignment",
        )
        self.assertEqual(
            adoptions[0]["resynchronization_attribution"],
            "direct_offset_page_alignment",
        )
        self.assertEqual(adoptions[0]["base_to_alternate_page_delta"], "1")
        self.assertEqual(adoptions[0]["alternate_page"], "2")

    def test_alternate_witness_scans_forward_across_rewrapped_page(self) -> None:
        merged_text = "ཞེས་ žes koṅ po\n\fཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "dummy page\n"
            "=== page 002 ===\n"
            "ཞེས་ žes\n"
            "koṅ po\n"
            "=== page 003 ===\n"
            "ཀོང་ koṅ po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes koṅ po", corrected)
        self.assertIn("\fཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_advances_after_unaligned_page(self) -> None:
        merged_text = "ཀ་ ka\nཁ་ kha\n\fཞེས་ zes\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "unrelated witness material 1\n"
            "=== page 002 ===\n"
            "unrelated witness material 2\n"
            "=== page 003 ===\n"
            "unrelated witness material 3\n"
            "=== page 004 ===\n"
            "unrelated witness material 4\n"
            "=== page 005 ===\n"
            "unrelated witness material 5\n"
            "=== page 006 ===\n"
            "ཞེས་ žes\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("\fཞེས་ źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 1)
        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(unresolved[0]["base_line"], "searched_alternate_pages=1-5")
        self.assertIn("1:", unresolved[0]["alternate_line"])
        self.assertIn("5:", unresolved[0]["alternate_line"])

    def test_alternate_witness_prefers_best_aligned_page_over_edge_match(self) -> None:
        merged_text = (
            "ཀ་ ka\n"
            "ཁ་ kha\n"
            "ག་ ga\n"
            "ཞེས་ zes\n"
            "ཅ་ ca\n"
            "ཆ་ cha\n"
            "ཇ་ ja\n"
        )
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཀ་ ka\n"
            "ཁ་ kha\n"
            "ག་ ga\n"
            "completely unrelated witness line\n"
            "ཅ་ ca\n"
            "ཆ་ cha\n"
            "ཇ་ ja\n"
            "=== page 002 ===\n"
            "ཀ་ ka\n"
            "ཁ་ kha\n"
            "ག་ ga\n"
            "ཞེས་ žes\n"
            "ཅ་ ca\n"
            "ཆ་ cha\n"
            "ཇ་ ja\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertNotIn("zes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rejects_page_with_only_one_compatible_line(self) -> None:
        merged_text = "ཞེས་ žes\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes\n"
            "completely unrelated witness text\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("žes", corrected)
        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "unalignable_page_content")

    def test_alternate_witness_aligns_normalized_non_token_fragments(self) -> None:
        merged_text = "ཞེས་ žes (Mvy 1)\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes(MVY 1)\n"
            "ཀོང་ koň po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertEqual(corrected.splitlines(), ["ཞེས་ źes (Mvy 1)", "ཀོང་ koṅ po"])
        self.assertNotIn("MVY", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_ignores_google_separator_junk_line(self) -> None:
        merged_text = "ཞེས་ žes (Mvy 1)\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes(MVY 1)\n"
            "::\n"
            "ཀོང་ koň po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertEqual(corrected.splitlines(), ["ཞེས་ źes (Mvy 1)", "ཀོང་ koṅ po"])
        self.assertNotIn("MVY", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_aligns_reordered_same_page_lines(self) -> None:
        merged_text = "ཀོང་ koṅ po\nཞེས་ žes (Mvy 1)\nབཀྲ་ bkra\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes(MVY 1)\n"
            "ཀོང་ koň po\n"
            "བཀྲ་ bkra\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertEqual(corrected.splitlines(), ["ཀོང་ koṅ po", "ཞེས་ źes (Mvy 1)", "བཀྲ་ bkra"])
        self.assertNotIn("MVY", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rejects_nonempty_line_loss(self) -> None:
        merged_text = "ཞེས་ žes\nཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("žes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "unalignable_rewrapped_page")
        self.assertEqual(unresolved[0]["base_key"], "2")
        self.assertEqual(unresolved[0]["alternate_key"], "1")

    def test_alternate_witness_aligns_reverse_rewrapped_page(self) -> None:
        merged_text = "ཞེས་ žes (Mvy 1)\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes(MVY 1) ཀོང་ koň po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertEqual(corrected.splitlines(), ["ཞེས་ źes (Mvy 1)", "ཀོང་ koṅ po"])
        self.assertNotIn("MVY", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rewrapped_same_page_fallback_unlocks_token_adoption(
        self,
    ) -> None:
        merged_text = (
            "ཀ་ ka alpha bravo charlie delta\n"
            "ཁ་ kha echo foxtrot golf hotel\n"
            "ག་ ga india juliet kilo lima\n"
            "ང་ nga mike november oscar papa\n"
            "ཞེས་ zes quebec romeo sierra tango\n"
            "ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཀ་ ka alpha bravo charlie delta ཁ་ kha echo foxtrot golf hotel "
            "ག་ ga india juliet kilo lima ང་ nga mike november oscar papa\n"
            "ཞེས་ žes quebec romeo sierra tango ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ źes quebec", corrected)
        self.assertNotIn("ཞེས་ zes quebec", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="",
            encoding="utf-8",
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "zes")
        self.assertEqual(adoptions[0]["alternate_token"], "źes")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_fricative_upgrade",
        )
        self.assertEqual(adoptions[0]["alignment_method"], "recovered_rewrapped_page")
        self.assertEqual(
            adoptions[0]["alignment_attribution"],
            "recovered_rewrapped_fallback",
        )
        self.assertEqual(
            adoptions[0]["resynchronization_attribution"],
            "direct_recovered_rewrapped_fallback",
        )
        self.assertEqual(adoptions[0]["base_to_alternate_page_delta"], "0")
        self.assertEqual(adoptions[0]["alternate_page"], "1")
        self.assertGreaterEqual(float(adoptions[0]["page_match_score"]), 0.50)
        self.assertGreaterEqual(float(adoptions[0]["canonical_overlap"]), 0.35)
        self.assertGreaterEqual(int(adoptions[0]["shared_canonical_tokens"]), 10)

    def test_alternate_witness_same_page_after_rewrapped_fallback_is_not_downstream(
        self,
    ) -> None:
        merged_text = (
            "ཀ་ ka alpha bravo charlie delta\n"
            "ཁ་ kha echo foxtrot golf hotel\n"
            "ག་ ga india juliet kilo lima\n"
            "ང་ nga mike november oscar papa\n"
            "ཞེས་ zes quebec romeo sierra tango\n"
            "ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
            "\f"
            "ཞེས་ žes downstream alpha bravo charlie delta\n"
        )
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཀ་ ka alpha bravo charlie delta ཁ་ kha echo foxtrot golf hotel "
            "ག་ ga india juliet kilo lima ང་ nga mike november oscar papa\n"
            "ཞེས་ žes quebec romeo sierra tango ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
            "=== page 002 ===\n"
            "ཞེས་ žes downstream alpha bravo charlie delta\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ źes quebec", corrected)
        self.assertIn("ཞེས་ źes downstream", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 2)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="",
            encoding="utf-8",
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        rows_by_page = {row["page"]: row for row in adoptions}
        self.assertEqual(
            rows_by_page["1"]["resynchronization_attribution"],
            "direct_recovered_rewrapped_fallback",
        )
        self.assertEqual(rows_by_page["2"]["alignment_method"], "ordinary_page_alignment")
        self.assertEqual(
            rows_by_page["2"]["alignment_attribution"],
            "ordinary_page_alignment",
        )
        self.assertEqual(
            rows_by_page["2"]["resynchronization_attribution"],
            "direct_page_alignment",
        )
        self.assertEqual(rows_by_page["2"]["resynchronization_source"], "")
        self.assertEqual(rows_by_page["2"]["base_to_alternate_page_delta"], "0")

        shifted_merged_text = (
            "ཀ་ ka alpha bravo charlie delta\n"
            "ཁ་ kha echo foxtrot golf hotel\n"
            "ག་ ga india juliet kilo lima\n"
            "ང་ nga mike november oscar papa\n"
            "ཞེས་ zes quebec romeo sierra tango\n"
            "ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
            "\f"
            "ཞེས་ žes shifted alpha bravo charlie delta\n"
        )
        shifted_alternate_merged_text = (
            "=== page 001 ===\n"
            "unrelated witness material alpha beta gamma\n"
            "=== page 002 ===\n"
            "ཀ་ ka alpha bravo charlie delta ཁ་ kha echo foxtrot golf hotel "
            "ག་ ga india juliet kilo lima ང་ nga mike november oscar papa\n"
            "ཞེས་ žes quebec romeo sierra tango ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
            "=== page 003 ===\n"
            "ཞེས་ žes shifted alpha bravo charlie delta\n"
        )

        shifted_result, shifted_corrected, _ = self.run_postprocess_fixture(
            shifted_merged_text,
            alternate_merged_text=shifted_alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ źes quebec", shifted_corrected)
        self.assertIn("ཞེས་ źes shifted", shifted_corrected)
        self.assertEqual(shifted_result["alternate_witness_adoptions"], 2)
        self.assertEqual(shifted_result["alternate_witness_unresolved"], 0)

        with Path(shifted_result["alternate_witness_adoptions_tsv"]).open(
            newline="",
            encoding="utf-8",
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        rows_by_page = {row["page"]: row for row in adoptions}
        self.assertEqual(
            rows_by_page["1"]["resynchronization_attribution"],
            "direct_recovered_rewrapped_fallback",
        )
        self.assertEqual(rows_by_page["1"]["base_to_alternate_page_delta"], "1")
        self.assertEqual(rows_by_page["1"]["alternate_page"], "2")
        self.assertEqual(rows_by_page["2"]["alignment_method"], "ordinary_page_alignment")
        self.assertEqual(
            rows_by_page["2"]["alignment_attribution"],
            "ordinary_page_alignment",
        )
        self.assertEqual(
            rows_by_page["2"]["resynchronization_attribution"],
            "downstream_after_recovered_rewrapped_fallback",
        )
        self.assertEqual(
            rows_by_page["2"]["resynchronization_source"],
            "recovered_rewrapped_base_page=1;alternate_page=2",
        )
        self.assertEqual(rows_by_page["2"]["base_to_alternate_page_delta"], "1")
        self.assertEqual(rows_by_page["2"]["alternate_page"], "3")

    def test_alternate_witness_rewrapped_fallback_keeps_base_line_text_with_noise(
        self,
    ) -> None:
        merged_text = (
            "ཀ་ ka alpha bravo charlie delta\n"
            "ཁ་ kha echo foxtrot golf hotel\n"
            "ག་ ga india juliet kilo lima\n"
            "ང་ nga mike november oscar papa\n"
            "ཞེས་ zes quebec romeo sierra tango\n"
            "ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )
        alternate_merged_text = (
            "=== page 001 ===\n"
            "12345 NOISE ཀ་ ka alpha bravo charlie delta ཁ་ kha echo foxtrot golf hotel "
            "ག་ ga india juliet kilo lima ང་ nga mike november oscar papa\n"
            "ཞེས་ žes quebec romeo sierra tango ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཀ་ ka alpha bravo charlie delta", corrected)
        self.assertIn("ཞེས་ źes quebec", corrected)
        self.assertNotIn("12345", corrected)
        self.assertNotIn("NOISE", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rewrapped_offset_page_does_not_trigger_fallback(
        self,
    ) -> None:
        merged_text = (
            "ཀ་ ka alpha bravo charlie delta\n"
            "ཁ་ kha echo foxtrot golf hotel\n"
            "ག་ ga india juliet kilo lima\n"
            "ང་ nga mike november oscar papa\n"
            "ཞེས་ zes quebec romeo sierra tango\n"
            "ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )
        matching_rewrapped_page = (
            "ཀ་ ka alpha bravo charlie delta ཁ་ kha echo foxtrot golf hotel "
            "ག་ ga india juliet kilo lima ང་ nga mike november oscar papa\n"
            "ཞེས་ žes quebec romeo sierra tango ཅ་ ca uniform victor whiskey xray\n"
            "ཆ་ cha yankee zulu amber beryl\n"
            "ཇ་ ja cedar dahlia ember fern\n"
        )
        alternate_merged_text = (
            "=== page 001 ===\n"
            "unrelated witness material alpha beta gamma\n"
            "=== page 002 ===\n"
            "unrelated witness material delta epsilon zeta\n"
            "=== page 003 ===\n"
            "unrelated witness material eta theta iota\n"
            "=== page 004 ===\n"
            f"{matching_rewrapped_page}"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ zes quebec", corrected)
        self.assertNotIn("ཞེས་ źes quebec", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

    def test_alternate_witness_does_not_adopt_loc_loss(self) -> None:
        merged_text = "གཉིས་ gñis\n"
        alternate_merged_text = "=== page 001 ===\nགཉིས་ gnis\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gñis", corrected)
        self.assertNotIn("gnis", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "gñis")
        self.assertEqual(unresolved[0]["alternate_token"], "gnis")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_does_not_adopt_loc_loss_in_gner(self) -> None:
        merged_text = "གཉེར་ gñer\n"
        alternate_merged_text = "=== page 001 ===\nགཉེར་ gner\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gñer", corrected)
        self.assertNotIn("gner", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "gñer")
        self.assertEqual(unresolved[0]["alternate_token"], "gner")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_adopts_citation_siglum_upgrade(self) -> None:
        merged_text = "mdo sde (Vi$T 3)\n"
        alternate_merged_text = "=== page 001 ===\nmdo sde (ViśT 3)\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ViśT", corrected)
        self.assertNotIn("Vi$T", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)
        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "Vi$T")
        self.assertEqual(adoptions[0]["alternate_token"], "ViśT")
        self.assertEqual(
            adoptions[0]["reason"], "alternate_witness_citation_siglum"
        )

    def test_alternate_witness_adopts_citation_cleanup_upgrade(self) -> None:
        merged_text = "vgl. lSK 12\n"
        alternate_merged_text = "=== page 001 ===\nvgl. ISK 12\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ISK", corrected)
        self.assertNotIn("lSK", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)
        with Path(result["alternate_witness_adoptions_tsv"]).open(
            newline="", encoding="utf-8"
        ) as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "lSK")
        self.assertEqual(adoptions[0]["alternate_token"], "ISK")
        self.assertEqual(
            adoptions[0]["reason"], "alternate_witness_citation_cleanup"
        )

    def test_high_risk_token_regressions(self) -> None:
        merged_text = (
            "ཀོང་ $in po\n"
            "dgra-Iba-Gottheit dPal-Idan g$egs $in tu dga'o dpe'i gañdza\n"
            "ཁོ་ kho\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("śin tu", corrected)
        self.assertNotIn("śiṅ tu", corrected)
        self.assertIn("dgra-lba-Gottheit", corrected)
        self.assertIn("dPal-ldan", corrected)
        self.assertIn("gśegs", corrected)
        self.assertIn("dga'o", corrected)
        self.assertIn("dpe'i", corrected)
        self.assertIn("gañdza", corrected)

        reasons = {(row["from_token"].lower(), row["to_token"].lower(), row["reason"]) for row in changes}
        self.assertIn(("$in", "śin", "explicit_user_allowlist_in_tu"), reasons)
        self.assertIn(("dgra-iba-gottheit", "dgra-lba-gottheit", "explicit_user_allowlist"), reasons)
        self.assertIn(("dpal-idan", "dpal-ldan", "explicit_user_allowlist"), reasons)
        self.assertIn(("g$egs", "gśegs", "explicit_user_allowlist"), reasons)
        self.assertEqual(result["tier_b_suggestions"], 0)

    def test_hard_guard_blocks_particle_suffix_drop(self) -> None:
        self.assertEqual(
            pem.rewrite_hard_guard_block_reason("dga'o", "dga", "test_reason", stage="entry"),
            "particle_suffix_drop",
        )
        self.assertEqual(
            pem.rewrite_hard_guard_block_reason("dpe'i", "dpe", "test_reason", stage="entry"),
            "particle_suffix_drop",
        )

    def test_sigla_registry_load_smoke(self) -> None:
        self.assertTrue(pem.SIGLA_REGISTRY_PATH.exists())
        canonical, confusable = pem.load_sigla_registry(pem.SIGLA_REGISTRY_PATH)
        self.assertIn("Bu-śz", canonical)
        self.assertIn("Gś-H", canonical)
        self.assertIn("Liś", canonical)
        self.assertIn("ViśT", canonical)
        self.assertIn("Yś", canonical)
        self.assertNotIn("Bu-Sz", canonical)
        self.assertNotIn("Gs-H", canonical)
        self.assertNotIn("VisT", canonical)
        self.assertNotIn("Ys", canonical)
        self.assertEqual(confusable.get("bu-$z"), "Bu-śz")
        self.assertEqual(confusable.get("bu-sz"), "Bu-śz")
        self.assertEqual(confusable.get("g$-h"), "Gś-H")
        self.assertEqual(confusable.get("gs-h"), "Gś-H")
        self.assertEqual(confusable.get("lís"), "Liś")
        self.assertEqual(confusable.get("vi$t"), "ViśT")
        self.assertEqual(confusable.get("vist"), "ViśT")
        self.assertEqual(confusable.get("y$"), "Yś")
        self.assertEqual(confusable.get("ys"), "Yś")

    def test_citation_sigla_confusables_normalized(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(NOBEL 1950:12) L$dz L$dz-K Vi$T Vi$ST Vis$T Li$ Lis$ Y$' Lis Lsdz Lsdz-K Lsdz-R\n"
            "vgl. (NOBEL 1951:13) L$dz Vi$T Vis$T Y$ Lis Lsdz\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Lśdz", corrected)
        self.assertIn("Lśdz-K", corrected)
        self.assertIn("Lśdz-R", corrected)
        self.assertIn("ViśT", corrected)
        self.assertIn("Liś", corrected)
        self.assertIn("Yś'", corrected)
        self.assertIn("Yś", corrected)
        self.assertNotIn("L$dz", corrected)
        self.assertNotIn("Vi$T", corrected)
        self.assertNotIn("Vi$ST", corrected)
        self.assertNotIn("Vis$T", corrected)
        self.assertNotIn("Li$", corrected)
        self.assertNotIn("Lis$", corrected)
        self.assertNotIn("Y$", corrected)
        self.assertNotIn(" Lis ", corrected)
        self.assertNotIn(" Lsdz", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("L$dz", "Lśdz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("L$dz-K", "Lśdz-K", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$T", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$ST", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$T", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lis$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Y$", "Yś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lis", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz", "Lśdz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz-K", "Lśdz-K", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz-R", "Lśdz-R", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_y_dollar_cue_without_year_or_siglum_word_boundary(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "sowie Durst bei Austrocknung“ (Y$ 96c).\n"
            "die Weisen als Wirkungen der Galle“ (Y$\n"
            "973); rna mchog 977/$ po'i ltag pa\n"
            "Gewalt gebracht“ (Li$ 17,10; KlonD 739,6;\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Yś 96c).", corrected)
        self.assertIn("(Yś", corrected)
        self.assertIn("(Liś 17,10; KlonD 739,6;", corrected)
        self.assertNotIn("Y$", corrected)
        self.assertNotIn("Li$", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Y$", "Yś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Liś", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_context_gate_keeps_lexical_lis(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "NOBEL 1950 lorem ipsum dolor sit amet consectetur adipisicing elit Lis.\n"
            "vgl. (Lis 30,2) und sonstiges.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("elit Lis.", corrected)
        self.assertIn("(Liś 30,2)", corrected)

        lis_siglum_changes = [
            row
            for row in changes
            if row["from_token"] == "Lis"
            and row["to_token"] == "Liś"
            and row["reason"] == "citation_siglum_confusable_map"
        ]
        self.assertEqual(len(lis_siglum_changes), 1)

    def test_citation_sigla_extended_safe_normalization(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(P$ 7c) (Bu-$z 51,3) (Vi$ 67b) (Vis$ 6b) ($ambh 5b6) ($PS 38) "
            "(RoIN$ 35,1) (In$ 29) (G$ 93a) (G$-H 481) (G$S-H 74a) (L1$ 30,2) (1.$dz 69,2) "
            "(ISK 5a) (1ISK 6b)\n"
            "(ViST 228,30) (VisST 142,4) (VIST 158,23) (VIiST 210,6) (YS 80d) (GS-H 60d)\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Ps 7c)", corrected)
        self.assertIn("(Bu-śz 51,3)", corrected)
        self.assertIn("(Vis 67b)", corrected)
        self.assertIn("(Vis 6b)", corrected)
        self.assertIn("(Śambh 5b6)", corrected)
        self.assertIn("(SPS 38)", corrected)
        self.assertIn("(RoINS 35,1)", corrected)
        self.assertIn("(Ins 29)", corrected)
        self.assertIn("(Gs 93a)", corrected)
        self.assertIn("(Gś-H 481)", corrected)
        self.assertIn("(Gś-H 74a)", corrected)
        self.assertIn("(ViśT 228,30)", corrected)
        self.assertIn("(ViśT 142,4)", corrected)
        self.assertIn("(ViśT 158,23)", corrected)
        self.assertIn("(ViśT 210,6)", corrected)
        self.assertIn("(Yś 80d)", corrected)
        self.assertIn("(Gś-H 60d)", corrected)
        self.assertIn("(Liś 30,2)", corrected)
        self.assertIn("(1.śdz 69,2)", corrected)
        self.assertIn("(1SK 5a)", corrected)
        self.assertIn("(1SK 6b)", corrected)

        self.assertNotIn("(P$ 7c)", corrected)
        self.assertNotIn("(Bu-$z 51,3)", corrected)
        self.assertNotIn("(Vi$ 67b)", corrected)
        self.assertNotIn("(Vis$ 6b)", corrected)
        self.assertNotIn("($ambh 5b6)", corrected)
        self.assertNotIn("($PS 38)", corrected)
        self.assertNotIn("(RoIN$ 35,1)", corrected)
        self.assertNotIn("(In$ 29)", corrected)
        self.assertNotIn("(G$ 93a)", corrected)
        self.assertNotIn("(G$-H 481)", corrected)
        self.assertNotIn("(G$S-H 74a)", corrected)
        self.assertNotIn("(ViST 228,30)", corrected)
        self.assertNotIn("(VisST 142,4)", corrected)
        self.assertNotIn("(VIST 158,23)", corrected)
        self.assertNotIn("(VIiST 210,6)", corrected)
        self.assertNotIn("(YS 80d)", corrected)
        self.assertNotIn("(GS-H 60d)", corrected)
        self.assertNotIn("(L1$ 30,2)", corrected)
        self.assertNotIn("(1.$dz 69,2)", corrected)
        self.assertNotIn("(ISK 5a)", corrected)
        self.assertNotIn("(1ISK 6b)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("P$", "Ps", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Bu-$z", "Bu-śz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("$ambh", "Śambh", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("$PS", "SPS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoIN$", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("In$", "Ins", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$", "Gs", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$-H", "Gś-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$S-H", "Gś-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("ViST", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VisST", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VIST", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VIiST", "ViśT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("YS", "Yś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("GS-H", "Gś-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("L1$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("ISK", "1SK", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("1ISK", "1SK", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_standalone_and_split_lines(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "$Sambh\n"
            "RoIN$\n"
            "vgl. „x“ (P$ Kolophon);\n"
            "„y“ (Bu-$2\n"
            "22,9); z\n"
            "„z“ (X$ 68d);\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Śambh", corrected)
        self.assertIn("RoINS", corrected)
        self.assertIn("(Ps Kolophon)", corrected)
        self.assertIn("(Bu-śz", corrected)
        self.assertIn("(Xs 68d)", corrected)
        self.assertNotIn("$Sambh", corrected)
        self.assertNotIn("RoIN$", corrected)
        self.assertNotIn("(P$ Kolophon)", corrected)
        self.assertNotIn("(Bu-$2", corrected)
        self.assertNotIn("(X$ 68d)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("$Sambh", "Śambh", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoIN$", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("P$", "Ps", "citation_siglum_confusable_map"), reasons)
        self.assertTrue(
            any(
                from_tok in {"Bu-$2", "Bu-$"}
                and to_tok == "Bu-śz"
                and reason == "citation_siglum_confusable_map"
                for from_tok, to_tok, reason in reasons
            )
        )
        self.assertIn(("X$", "Xs", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_doll_roins_and_bhullg_guardrails(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Doll\n"
            "RoINs\n"
            "vgl. (Doll 12,4) und (RoINs 7,1) und (RoINSs 21,9) und (BhuLlg 33,2).\n"
            "Eine Puppe heißt Doll im Englischen.\n"
            "Bhulg und BhuLg bleiben.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("\nDol1\n", corrected)
        self.assertIn("\nRoINS\n", corrected)
        self.assertIn("(Dol1 12,4)", corrected)
        self.assertIn("(RoINS 7,1)", corrected)
        self.assertIn("(RoINS 21,9)", corrected)
        self.assertIn("(BhuLg 33,2)", corrected)
        self.assertIn("Eine Puppe heißt Doll im Englischen.", corrected)
        self.assertIn("Bhulg und BhuLg bleiben.", corrected)
        self.assertNotIn("(Doll 12,4)", corrected)
        self.assertNotIn("(RoINs 7,1)", corrected)
        self.assertNotIn("(RoINSs 21,9)", corrected)
        self.assertNotIn("(BhuLlg 33,2)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Doll", "Dol1", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoINs", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoINSs", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("BhuLlg", "BhuLg", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_do_not_uppercase_german_ins_before_sanskrit(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Er ging ins skt. Nirväna; siehe (In$ 29) und (Ins 30).\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("ins skt. Nirvāṇa", corrected)
        self.assertIn("(Ins 29)", corrected)
        self.assertIn("(Ins 30)", corrected)
        self.assertNotIn("Ins skt. Nirvāṇa", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("ins", "Ins", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("In$", "Ins", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Nirväna", "Nirvāṇa", "sanskrit_high_freq_allowlist"), reasons)

    def test_sigla_standalone_allowlist_applies_on_base_citation_lines(self) -> None:
        self.assertTrue(
            pem.token_has_siglum_context(
                "Doll",
                "Doll",
                0,
                4,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )
        self.assertTrue(
            pem.token_has_siglum_context(
                "RoINs",
                "RoINs",
                0,
                5,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )
        self.assertFalse(
            pem.token_has_siglum_context(
                "Haus",
                "Haus",
                0,
                4,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )

    def test_citation_sigla_allowlist_applies_in_frontmatter_entry_zero(self) -> None:
        merged_text = (
            "Doll\n"
            "RoINs\n"
            "SCHMIDT 1841 (Tibetisch-Deutsches Wörterbuch).\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("\nDol1\n", f"\n{corrected}")
        self.assertIn("\nRoINS\n", f"\n{corrected}")
        self.assertNotIn("\nDoll\n", f"\n{corrected}")
        self.assertNotIn("\nRoINs\n", f"\n{corrected}")

    def test_citation_sigla_allowlist_open_paren_wrap_context(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "vgl. (RoINs 7,1).\n"
            "weitere Stelle (Doll\n"
            "24,21) im Kontext.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(RoINS 7,1).", corrected)
        self.assertIn("(Dol1\n24,21)", corrected)
        self.assertNotIn("(RoINs 7,1).", corrected)
        self.assertNotIn("(Doll\n24,21)", corrected)

    def test_citation_sigla_allowlist_formfeed_wrap_context(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "weitere Stelle (Doll\f"
            "24,21) im Kontext.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Dol1\f24,21)", corrected)
        self.assertNotIn("(Doll\f24,21)", corrected)

    def test_citation_sigla_allowlist_intro_list_context(self) -> None:
        merged_text = (
            "Die verwendeten Abkürzungen sind historisch gewachsen.\n"
            "Texte in Sammelbänden wurden ebenfalls durchnumeriert "
            "(Bb33, Bb45, Doll, Dol3 usw.).\n"
            "Eine Puppe heißt Doll im Englischen.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Bb33, Bb45, Dol1, Dol3 usw.)", corrected)
        self.assertIn("Eine Puppe heißt Doll im Englischen.", corrected)
        self.assertNotIn("(Bb33, Bb45, Doll, Dol3 usw.)", corrected)

    def test_german_dotless_i_extended_safe_map_and_numeric(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Eın Artıkel ıst 111 den Fällen und 1111 Oktober publızıert.\n"
            "Dıes dıeserlei dıejenigen Wırkung Stıftung Bıld Schrıft Schrıftsprache Tıbetisch Tıbetologen.\n"
            "lexıkographisch und lexıkalisch in der Kommunıikation der Verwaltıng.\n"
            "Bıographie und bıographisch; nıeder, nıederlassen, vernıchten, gelıngen.\n"
            "Seı beı der Basıs und Iranıstik beschleunıgen.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Ein Artikel ist in den Fällen und im Oktober publiziert.", corrected)
        self.assertIn(
            "Dies dieserlei diejenigen Wirkung Stiftung Bild Schrift Schriftsprache Tibetisch Tibetologen.",
            corrected,
        )
        self.assertIn("lexikographisch und lexikalisch in der Kommunikation der Verwaltung.", corrected)
        self.assertIn("Biographie und biographisch; nieder, niederlassen, vernichten, gelingen.", corrected)
        self.assertIn("Sei bei der Basis und Iranistik beschleunigen.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Eın", "Ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Artıkel", "Artikel", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("111", "in", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("1111", "im", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("publızıert", "publiziert", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Basıs", "Basis", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Iranıstik", "Iranistik", "german_dotless_i_safe_map"), reasons)

    def test_citation_name_safe_map(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(NOBEL 1950:12) Tromas Wyrıe Pangiunc Pangiung Stem Kvzrne Engliish oftheIndo-Aryan "
            "VoceL RicHarpson JAscake.\n"
            "Das Stem bleibt in der Prosa unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(NOBEL 1950:12) Thomas Wylie Panglung Panglung Stein Kværne English of the Indo-Aryan", corrected)
        self.assertIn("VoceL RicHarpson JAscake.", corrected)
        self.assertIn("Das Stem bleibt in der Prosa unverändert.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Tromas", "Thomas", "citation_name_safe_map"), reasons)
        self.assertIn(("Wyrıe", "Wylie", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangiunc", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangiung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Stem", "Stein", "citation_name_safe_map"), reasons)
        self.assertIn(("Kvzrne", "Kværne", "citation_name_safe_map"), reasons)

    def test_citation_safe_map_extended_bibliography_cleanup(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(SCHMIDT 1902:7) UesachH UzsachH Pansiung Pansıung PangLung Cürpers Denwoop Schwirger Granmatik "
            "Hindn Into SreinGass ZongrTse Dierz manuseript Vollkommenbeiten Ihe Iwo accompaniedbya.\n"
            "(SCHMIDT 1902:8) Pangıunc.\n"
            "(STEIN 1961:4) P rsian-English vice versä.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "(SCHMIDT 1902:7) Uebach Uebach Panglung Panglung Panglung Cüppers Denwood Schwieger Grammatik "
            "Hindu into Steingass Zongtse Dietz manuscript Vollkommenheiten The Two accompanied by a.",
            corrected,
        )
        self.assertIn("(SCHMIDT 1902:8) Panglung.", corrected)
        self.assertIn("(STEIN 1961:4) Persian-English vice versa.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("UesachH", "Uebach", "citation_name_safe_map"), reasons)
        self.assertIn(("UzsachH", "Uebach", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansiung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansıung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangıunc", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("PangLung", "Panglung", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("SreinGass", "Steingass", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Into", "into", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Ihe", "The", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Iwo", "Two", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("accompaniedbya", "accompanied by a", "citation_english_spacing_loss_map"), reasons)
        self.assertIn(("P rsian-English", "Persian-English", "citation_phrase_safe_map"), reasons)
        self.assertIn(("vice versä", "vice versa", "citation_phrase_safe_map"), reasons)

    def test_bibliography_author_year_and_continuation_lines_are_citation_like(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Schwirger, Peter 20092. Handbuch zur Granmatik der klassischen tibetischen Schrift-\n"
            "for the conversion of Hindu and Muhammadan Into A.D. dates, and vice versä.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "Schwieger, Peter 20092. Handbuch zur Grammatik der klassischen tibetischen Schrift-",
            corrected,
        )
        self.assertIn(
            "for the conversion of Hindu and Muhammadan into A.D. dates, and vice versa.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Schwirger", "Schwieger", "citation_name_safe_map"), reasons)
        self.assertIn(("Granmatik", "Grammatik", "citation_name_safe_map"), reasons)
        self.assertIn(("Into", "into", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("vice versä", "vice versa", "citation_phrase_safe_map"), reasons)

    def test_bibliography_continuations_and_gloss_lines_get_narrow_context_fixes(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "3. ıch, für skt. abam.\n"
            "1. sıch niederlassen.\n"
            "geraten, sıch untereinander nicht einig wer-\n"
            "will ıch zuerst vernichten (Mil 66,9).\n"
            "tig, ıch diente ihr (Bca 7.52b).\n"
            "Säkya-mchog-ldan. Reproduced from the unique manuseript prepared in the library.\n"
            "tische Text unter Mitarbeit von Siglinde Dierz hg. v. Champa Thupten ZongrTse.\n"
            "— /Pansiung, Lokesh Chandra 1982.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("3. ich, für skt. abam.", corrected)
        self.assertIn("1. sich niederlassen.", corrected)
        self.assertIn("geraten, sich untereinander nicht einig wer-", corrected)
        self.assertIn("will ich zuerst vernichten (Mil 66,9).", corrected)
        self.assertIn("tig, ich diente ihr (Bca 7.52b).", corrected)
        self.assertIn("Reproduced from the unique manuscript prepared in the library.", corrected)
        self.assertIn("Siglinde Dietz hg. v. Champa Thupten Zongtse.", corrected)
        self.assertIn("— /Panglung, Lokesh Chandra 1982.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("ıch", "ich", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("sıch", "sich", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("manuseript", "manuscript", "citation_name_safe_map"), reasons)
        self.assertIn(("Dierz", "Dietz", "citation_name_safe_map"), reasons)
        self.assertIn(("ZongrTse", "Zongtse", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansiung", "Panglung", "citation_name_safe_map"), reasons)

    def test_new_exact_german_function_word_and_dotless_i_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Wir sahen 6111 Blättern und €111 Beispiel, nicht aber ©111 42.\n"
            "cine cinem cinen ciner cines seı Eın eın ıst.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Wir sahen ein Blättern und ein Beispiel, nicht aber ©111 42.", corrected)
        self.assertIn("eine einem einen einer eines sei Ein ein ist.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("6111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("€111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertNotIn(("©111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("cine", "eine", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cinem", "einem", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cinen", "einen", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("ciner", "einer", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cines", "eines", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("seı", "sei", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Eın", "Ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("eın", "ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("ıst", "ist", "german_dotless_i_safe_map"), reasons)

    def test_new_exact_tibetan_allowlist_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "rmams breyud broyud broyad bsnal biin giien giier bsiien siian giis giiis griis miiam yiin fiid "
            "kyı kyıs gyı gyıs yın cıg gcıg zıg sıg dkyıl kyanı yanı byanı gsarı snanı sarıs garı Igarı\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "rnams brgyud brgyud brgyad bsṅal bźin gñen gñer bsñen sñan gñis gñis gñis mñam yin ñid "
            "kyi kyis gyi gyis yin cig gcig zig sig dkyil kyaṅ yaṅ byaṅ gsaṅ snaṅ saṅs gaṅ lgaṅ",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("rmams", "rnams", "explicit_user_allowlist"), reasons)
        self.assertIn(("breyud", "brgyud", "explicit_user_allowlist"), reasons)
        self.assertIn(("broyud", "brgyud", "explicit_user_allowlist"), reasons)
        self.assertIn(("broyad", "brgyad", "explicit_user_allowlist"), reasons)
        self.assertIn(("bsnal", "bsṅal", "explicit_user_allowlist"), reasons)
        self.assertIn(("biin", "bźin", "explicit_user_allowlist"), reasons)
        self.assertIn(("giien", "gñen", "explicit_user_allowlist"), reasons)
        self.assertIn(("giier", "gñer", "explicit_user_allowlist"), reasons)
        self.assertIn(("bsiien", "bsñen", "explicit_user_allowlist"), reasons)
        self.assertIn(("siian", "sñan", "explicit_user_allowlist"), reasons)
        self.assertIn(("giis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("giiis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("griis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("miiam", "mñam", "explicit_user_allowlist"), reasons)
        self.assertIn(("yiin", "yin", "explicit_user_allowlist"), reasons)
        self.assertIn(("fiid", "ñid", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyı", "kyi", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyıs", "kyis", "explicit_user_allowlist"), reasons)
        self.assertIn(("gyı", "gyi", "explicit_user_allowlist"), reasons)
        self.assertIn(("gyıs", "gyis", "explicit_user_allowlist"), reasons)
        self.assertIn(("yın", "yin", "explicit_user_allowlist"), reasons)
        self.assertIn(("cıg", "cig", "explicit_user_allowlist"), reasons)
        self.assertIn(("gcıg", "gcig", "explicit_user_allowlist"), reasons)
        self.assertIn(("zıg", "zig", "explicit_user_allowlist"), reasons)
        self.assertIn(("sıg", "sig", "explicit_user_allowlist"), reasons)
        self.assertIn(("dkyıl", "dkyil", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyanı", "kyaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("yanı", "yaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("byanı", "byaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("gsarı", "gsaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("snanı", "snaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("sarıs", "saṅs", "explicit_user_allowlist"), reasons)
        self.assertIn(("garı", "gaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("Igarı", "lgaṅ", "explicit_user_allowlist"), reasons)

    def test_new_tibetan_allowlist_does_not_spill_into_plain_german_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler wie kyanı oder yani oder zıg oder snanı oder garı oder Igarı soll hier nicht automatisch korrigiert werden.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "Ein Druckfehler wie kyanı oder yani oder zıg oder snanı oder garı oder Igarı soll hier nicht automatisch korrigiert werden.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("kyanı", "kyaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("zıg", "zig", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("snanı", "snaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("garı", "gaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("Igarı", "lgaṅ", "explicit_user_allowlist"), reasons)

    def test_tibetan_phrase_allowlist_rewrites_tshul_khrims(self) -> None:
        merged_text = (
            "ཚུལ་ཁྲིམས་ tshul khrims\n"
            "tsbul kbrims rnam par dag pa\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("tshul khrims rnam par dag pa", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("tsbul kbrims", "tshul khrims", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_does_not_rewrite_orphan_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler tsbul kbrims bleibt hier unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("tsbul kbrims", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            ("tsbul kbrims", "tshul khrims", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_dang_ldan_pa(self) -> None:
        merged_text = (
            "དང་ལྡན་པ་ daṅ ldan pa\n"
            "dan ldan pa yin no\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("daṅ ldan pa yin no", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_does_not_rewrite_dang_ldan_pa_in_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler dan ldan pa bleibt hier unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("dan ldan pa", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_recurring_dan_phrase_families(self) -> None:
        merged_text = (
            "དང་ daṅ\n"
            "khog phub dan bcas pa dan bcas par dan bcas pa'i dan bcas pas dan bcas kyi "
            "dri ma dan bral ba dan bral ba'i dan bral bas dan bral bar "
            "de dan 'dra ba de dan ’dra ba "
            "dan lhan cig dan mthun pa dan mthun par dan mthun pas don dan mthunpa "
            "dan ldan pa'i dan ldan pas dan ldan par\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "khog phub daṅ bcas pa daṅ bcas par daṅ bcas pa'i daṅ bcas pas daṅ bcas kyi "
            "dri ma daṅ bral ba daṅ bral ba'i daṅ bral bas daṅ bral bar "
            "de daṅ 'dra ba de daṅ ’dra ba "
            "daṅ lhan cig daṅ mthun pa daṅ mthun par daṅ mthun pas don daṅ mthun pa "
            "daṅ ldan pa'i daṅ ldan pas daṅ ldan par",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        for from_token, to_token in [
            ("dan bcas pa", "daṅ bcas pa"),
            ("dan bcas par", "daṅ bcas par"),
            ("dan bcas pa'i", "daṅ bcas pa'i"),
            ("dan bcas pas", "daṅ bcas pas"),
            ("dan bcas kyi", "daṅ bcas kyi"),
            ("dan bral ba", "daṅ bral ba"),
            ("dan bral ba'i", "daṅ bral ba'i"),
            ("dan bral bas", "daṅ bral bas"),
            ("dan bral bar", "daṅ bral bar"),
            ("dan 'dra", "daṅ 'dra"),
            ("dan ’dra", "daṅ ’dra"),
            ("dan lhan cig", "daṅ lhan cig"),
            ("dan mthun pa", "daṅ mthun pa"),
            ("dan mthun par", "daṅ mthun par"),
            ("dan mthun pas", "daṅ mthun pas"),
            ("dan mthunpa", "daṅ mthun pa"),
            ("dan ldan pa'i", "daṅ ldan pa'i"),
            ("dan ldan pas", "daṅ ldan pas"),
            ("dan ldan par", "daṅ ldan par"),
        ]:
            self.assertIn(
                (from_token, to_token, "tibetan_translit_phrase_allowlist"),
                reasons,
            )

    def test_tibetan_phrase_allowlist_does_not_rewrite_recurring_dan_families_in_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "dan bcas pa dan bral ba dan 'dra ba dan lhan cig dan mthun pa dan ldan pa'i\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "dan bcas pa dan bral ba dan 'dra ba dan lhan cig dan mthun pa dan ldan pa'i",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        for from_token, to_token in [
            ("dan bcas pa", "daṅ bcas pa"),
            ("dan bral ba", "daṅ bral ba"),
            ("dan 'dra", "daṅ 'dra"),
            ("dan lhan cig", "daṅ lhan cig"),
            ("dan mthun pa", "daṅ mthun pa"),
            ("dan ldan pa'i", "daṅ ldan pa'i"),
        ]:
            self.assertNotIn(
                (from_token, to_token, "tibetan_translit_phrase_allowlist"),
                reasons,
            )

    def test_tibetan_phrase_allowlist_rewrites_ting_nge_dzin_variants(self) -> None:
        merged_text = (
            "ཏིང་ངེ་འཛིན་ tiṅ ṅe 'dzin\n"
            "bar chad med pa' tin rre 'dzin la skyes.\n"
            "ston pas tin ne 'dzin rnam gsum.\n"
            "chub sems dpa'i tin ñe 'dzin gyi min.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("bar chad med pa' tiṅ ṅe 'dzin la skyes.", corrected)
        self.assertIn("ston pas tiṅ ṅe 'dzin rnam gsum.", corrected)
        self.assertIn("chub sems dpa'i tiṅ ṅe 'dzin gyi min.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        for from_token in ("tin rre 'dzin", "tin ne 'dzin", "tin ñe 'dzin"):
            self.assertIn(
                (
                    from_token,
                    "tiṅ ṅe 'dzin",
                    "tibetan_translit_ting_nge_dzin_phrase",
                ),
                reasons,
            )

    def test_tibetan_phrase_allowlist_does_not_rewrite_ting_nge_dzin_in_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Beispiel tin ne 'dzin bleibt hier unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("tin ne 'dzin bleibt hier unverändert", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            (
                "tin ne 'dzin",
                "tiṅ ṅe 'dzin",
                "tibetan_translit_ting_nge_dzin_phrase",
            ),
            reasons,
        )

    def test_tibetan_dang_phrase_override_rewrites_curated_phrase(self) -> None:
        merged_text = (
            "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can\n"
            "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun\n"
            "གང་དང་གང་ gan dan gan Tgan gan.\n"
            "གང་དང་ཡང་ gan dan yani \\gan yan.\n"
            "གང་དང་གང་ gar daṅ gaṅ Tgari gan.\n"
            "གང་དང་ཡང་ gaṅ daṅ yaṅ Igari yani.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("kun snan daṅ pa can, auch kun", corrected)
        self.assertIn("གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.", corrected)
        self.assertIn("གང་དང་ཡང་ gaṅ daṅ yaṅ \\gaṅ yaṅ.", corrected)
        self.assertIn("གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.", corrected)
        self.assertIn("གང་དང་ཡང་ gaṅ daṅ yaṅ lgaṅ yaṅ.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            (
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun",
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can, auch kun",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )
        self.assertIn(
            (
                "གང་དང་གང་ gan dan gan Tgan gan.",
                "གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )
        self.assertIn(
            (
                "གང་དང་ཡང་ gan dan yani \\gan yan.",
                "གང་དང་ཡང་ gaṅ daṅ yaṅ \\gaṅ yaṅ.",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )
        self.assertIn(
            (
                "གང་དང་གང་ gar daṅ gaṅ Tgari gan.",
                "གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )
        self.assertIn(
            (
                "གང་དང་ཡང་ gaṅ daṅ yaṅ Igari yani.",
                "གང་དང་ཡང་ gaṅ daṅ yaṅ Igaṅ yaṅ.",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )

    def test_tibetan_dang_phrase_override_does_not_rewrite_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "kun snan dan pa can, auch kun\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("kun snan dan pa can, auch kun", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            (
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun",
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can, auch kun",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )

    def test_boundary_safe_tibetan_l_cluster_and_bzi_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Ita Iha Ihan Iho Itos bii bii' bii’ bii'an bii’an bii'o bii’o bii'i bii’i fooItaBar\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "lta lha lhan lho ltos bźi bźi' bźi’ bźi'an bźi’an bźi'o bźi’o bźi'i bźi’i fooItaBar",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Ita", "lta", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Iha", "lha", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Ihan", "lhan", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Iho", "lho", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Itos", "ltos", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii", "bźi", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'", "bźi'", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’", "bźi’", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'an", "bźi'an", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’an", "bźi’an", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'o", "bźi'o", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’o", "bźi’o", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'i", "bźi'i", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’i", "bźi’i", "explicit_case_sensitive_allowlist"), reasons)

    def test_hyphenated_i_l_fixes_keep_loc_transliteration(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Brag-Iha dGra-Iha'i Bkra-śis-Ihun-po foo-IhaBar\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Brag-lha dGra-lha'i Bkra-śis-lhun-po foo-IhaBar", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Brag-Iha", "Brag-lha", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertIn(("dGra-Iha'i", "dGra-lha'i", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertIn(("Bkra-śis-Ihun-po", "Bkra-śis-lhun-po", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertNotIn(("fooItaBar", "fooltaBar", "explicit_case_sensitive_allowlist"), reasons)

    def test_tibetan_dang_witness_rewrites_latin_dan(self) -> None:
        merged_text = (
            "ཆུ་དང་ལྡན་པ་ chu dan ldan pa\n"
            "དང་པོ་ dan po\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("ཆུ་དང་ལྡན་པ་ chu daṅ ldan pa", corrected)
        self.assertIn("དང་པོ་ daṅ po", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_curated_x_dan_ldan_pa_forms(self) -> None:
        merged_text = (
            "ཆོས་ chos\n"
            "skal ba dan ldan pa rnams stobs dan ldan pas chos dan ldan pa'i "
            "dpal dbaṅ dan ldan pa yi stobs dan ldan pa de rnams chos dan ldan pa ma\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "skal ba daṅ ldan pa rnams stobs daṅ ldan pas chos daṅ ldan pa'i "
            "dpal dbaṅ daṅ ldan pa yi stobs daṅ ldan pa de rnams chos daṅ ldan pa ma",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("skal ba dan ldan pa", "skal ba daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("stobs dan ldan pa", "stobs daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("chos dan ldan pa", "chos daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("dbaṅ dan ldan pa", "dbaṅ daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_curated_x_dan_ldan_pa_on_german_heavy_line(self) -> None:
        merged_text = (
            "ཆོས་ chos\n"
            "1. auch stobs dan ldan pa stark, mächtig, berühmt und weithin bekannt.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "1. auch stobs daṅ ldan pa stark, mächtig, berühmt und weithin bekannt.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("stobs dan ldan pa", "stobs daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_dang_witness_does_not_touch_apostrophe_prefixed_dan(self) -> None:
        merged_text = "དང་ 'dan gsar\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("དང་ 'dan gsar", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("'dan", "'daṅ", "tibetan_dang_witness_rewrite"), reasons)

    def test_tibetan_headword_dang_witness_rewrites_latin_dan(self) -> None:
        merged_text = "འདང་ dan \\Vldan.\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("འདང་ daṅ \\Vldan.", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertTrue(
            ("dan", "daṅ", "tibetan_dang_witness_rewrite") in reasons
            or (
                "འདང་ dan \\Vldan.",
                "འདང་ daṅ \\Vldan.",
                "tibetan_dang_phrase_override",
            )
            in reasons
        )

    def test_tibetan_dang_witness_does_not_fire_without_tibetan(self) -> None:
        merged_text = "dan po gsal gi don\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("dan po gsal gi don", corrected)
        self.assertNotIn("daṅ po", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("dan", "daṅ", "tibetan_dang_witness_rewrite"), reasons)

    def test_exact_sanskrit_overrides_for_verified_forms(self) -> None:
        merged_text = (
            "སྐད skt. Nägärjuna Pramänakirtih Päramitäsamäsa Uddänas Mülasarvästiväda "
            "Mülasarvästi- Mahämäyürividyäräjni Astäpadikrtadhüpayoga Dhäpayoga-ratnamaälä\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "skt. Nāgārjuna Pramāṇakīrtiḥ Pāramitāsamāsa Uddānas Mūlasarvāstivāda "
            "Mūlasarvāsti- Mahāmāyūrīvidyārājñī Aṣṭapadīkṛtadhūpayoga Dhūpayogaratnamālā",
            corrected,
        )

        reasons = {(row["from_token"].lower(), row["to_token"].lower(), row["reason"]) for row in changes}
        self.assertIn(("dhäpayoga-ratnamaälä", "dhūpayogaratnamālā", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("nägärjuna", "nāgārjuna", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("pramänakirtih", "pramāṇakīrtiḥ", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("päramitäsamäsa", "pāramitāsamāsa", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("uddänas", "uddānas", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mülasarvästiväda", "mūlasarvāstivāda", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mülasarvästi", "mūlasarvāsti", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mahämäyürividyäräjni", "mahāmāyūrīvidyārājñī", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("astäpadikrtadhüpayoga", "aṣṭapadīkṛtadhūpayoga", "sanskrit_high_freq_allowlist"), reasons)

    def test_low_hanging_wts_8b_9m_sanskrit_overrides_are_exact(self) -> None:
        cases = [
            ("Prajnāpāramitā", "Prajñāpāramitā"),
            ("sarvajnatāpragbhārab", "sarvajñatāpragbhārab"),
            ("śrävaka", "śrāvaka"),
            ("śäntideva", "śāntideva"),
            ("indriyaparāparajnānabalam", "indriyaparāparajñānabalam"),
            ("Prajnāpāra", "Prajñāpāra"),
            ("śväsayema", "śvāsayema"),
            ("sarvajnatāprāgbhārab", "sarvajñatāprāgbhārab"),
            ("Satasāhasrikāprajnāpāramitā-Lesung", "Śatasāhasrikāprajñāpāramitā-Lesung"),
            ("Prajnāpāramitāsūtra", "Prajñāpāramitāsūtra"),
            ("prajnāpāramitāsūtra", "prajñāpāramitāsūtra"),
            ("Satasāhasrikāprajnāpāramitāsātra", "Śatasāhasrikāprajñāpāramitāsūtra"),
            ("Hunderttausender-Prajnāpāramitāsūrtra", "Hunderttausender-Prajñāpāramitāsūtra"),
            ("Prajnaptisāstra", "Prajñaptisāstra"),
            ("śrävakas", "śrāvakas"),
            ("śrävasti", "śrāvasti"),
            ("prajnāyate", "prajñāyate"),
            ("Prajnapāramitāsiitra", "Prajñāpāramitāsūtra"),
            ("rvijnānadhātub", "rvijñānadhātub"),
            ("anantäparyantab", "anantāparyantab"),
            ("Vaiśvänara", "Vaiśvānara"),
            ("Jnānagarbha", "Jñānagarbha"),
            ("śräva", "śrāva"),
            ("buddhajnanāadhyalambanatāyii", "buddhajñanāadhyalambanatāyii"),
            ("vādavidhijnena", "vādavidhijñena"),
            ("Śästras", "Śāstras"),
            ("śästras", "śāstras"),
        ]
        merged_text = "སྐད skt. " + " ".join(src for src, _ in cases) + "\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        for _, target in cases:
            self.assertIn(target, corrected)

        reasons = {(row["from_token"].lower(), row["to_token"].lower(), row["reason"]) for row in changes}
        for source, target in cases:
            self.assertIn((source.lower(), target.lower(), "sanskrit_high_freq_allowlist"), reasons)

    def test_residual_error_sanskrit_proper_name_and_term_overrides_are_exact(self) -> None:
        cases = [
            ("Säkyamuni", "Śākyamuni"),
            ("Śäkyamuni", "Śākyamuni"),
            ("Säkyamunis", "Śākyamunis"),
            ("Säkyamunii", "Śākyamuni"),
            ("Nirväna", "Nirvāṇa"),
            ("Nirväru", "Nirvāṇa"),
            ("Samsära", "Saṃsāra"),
            ("Sarnsära", "Saṃsāra"),
            ("Sanisära", "Saṃsāra"),
            ("Samisära", "Saṃsāra"),
            ("Samsara", "Saṃsāra"),
            ("Samsāra", "Saṃsāra"),
            ("desSamsära", "des Saṃsāra"),
            ("Samskäras", "Saṃskāras"),
        ]
        merged_text = "སྐད skt. " + " ".join(src for src, _ in cases) + "\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        for _, target in cases:
            self.assertIn(target, corrected)

        reasons = {
            (row["from_token"].lower(), row["to_token"].lower(), row["reason"])
            for row in changes
        }
        for source, target in cases[:6]:
            self.assertIn((source.lower(), target.lower(), "sanskrit_high_freq_allowlist"), reasons)
        for source, target in cases[6:]:
            self.assertIn((source.lower(), target.lower(), "sanskrit_promoted_context_gate"), reasons)

    def test_residual_error_sanskrit_overrides_do_not_add_broad_rules(self) -> None:
        merged_text = (
            "Eine deutsche Prosa mit Sakyamuni Nirvana Sämkhya "
            "fooäbar und Nirvänafest Samsärafest Samskärasfest "
            "desSamsärafest Samsarafest.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "Sakyamuni Nirvana Sämkhya fooäbar und Nirvänafest "
            "Samsärafest Samskärasfest desSamsärafest Samsarafest",
            corrected,
        )
        reasons = {row["reason"] for row in changes}
        self.assertNotIn("sanskrit_high_freq_allowlist", reasons)
        self.assertNotIn("sanskrit_promoted_context_gate", reasons)

    def test_samsara_samskara_terms_normalize_in_buddhist_term_context(self) -> None:
        merged_text = (
            "Samsära und Nirväna untrennbar eins werden.\n"
            '"indem der Strom desSamsära zerstört wird,\n'
            '"um\' bedeutet: Kontinuität der Samskäras"\n'
            "die Ebene des Samsara überschritten.\n"
            "die Ebene des Samsāra überschritten.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Saṃsāra und Nirvāṇa", corrected)
        self.assertIn("Strom des Saṃsāra", corrected)
        self.assertIn("Kontinuität der Saṃskāras", corrected)
        self.assertIn("Ebene des Saṃsāra", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        for source, target in [
            ("Samsära", "Saṃsāra"),
            ("desSamsära", "des Saṃsāra"),
            ("Samskäras", "Saṃskāras"),
            ("Samsara", "Saṃsāra"),
            ("Samsāra", "Saṃsāra"),
        ]:
            self.assertIn((source, target, "sanskrit_promoted_context_gate"), reasons)

    def test_promoted_sanskrit_overrides_preserve_exact_lowercase_forms(self) -> None:
        merged_text = "སྐད skt. Acavimśatikasahasrikä[prajnāpāramitāsūtra]\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Acavimśatikasahasrikä[prajñāpāramitāsūtra]", corrected)
        self.assertNotIn("Acavimśatikasahasrikä[Prajñāpāramitāsūtra]", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("prajnāpāramitāsūtra", "prajñāpāramitāsūtra", "sanskrit_high_freq_allowlist"),
            reasons,
        )

    def test_low_hanging_sanskrit_batch_does_not_add_broad_character_rules(self) -> None:
        merged_text = (
            "Eine deutsche Prosa mit Satafamilie, ajnana, xäy, foo-siitra, "
            "bar-sūrtra, rvijnana, sraevaka und nichttitelhafter Lesung.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertEqual(corrected.strip(), merged_text.strip())
        reasons = {row["reason"] for row in changes}
        self.assertNotIn("sanskrit_high_freq_allowlist", reasons)

    def test_structural_quote_wrap_direct(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "beispiel „sie vortra-\n"
            "gen das klar“ (Mil 12,3)\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("beispiel „sie vortragen das klar“ (Mil 12,3)", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("vortra-/gen", "vortragen", "structural_german_quote_hyphen_wrap_direct"),
            reasons,
        )

    def test_structural_quote_wrap_with_intervening_citation(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "tschJul khrims — gos gon pas (metr.) „sie tra-\n"
            "(Gir\n"
            "\n"
            "24,24); lta ba — gi 97/ gzun nas „man legt\n"
            "eine reine Sicht zu Grunde“ (Mil 86,27);\n"
            "khon chos pa — ciig yin par ’dug „er scheint\n"
            "\n"
            "gen das Gewand einer reinen Moral“\n"
            "\n"
            "ein wahrhaft religiöser Mensch zu sein“ (Mil 128,7)\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("„sie tragen das Gewand einer reinen Moral“ (Gir 24,24);", corrected)
        self.assertIn("lta ba — gi 97/ gzun nas „man legt", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("tra-/gen", "tragen", "structural_german_quote_hyphen_wrap_citation"),
            reasons,
        )

    def test_structural_quote_wrap_does_not_touch_bibliography(self) -> None:
        merged_text = (
            "Schmidt, Isaak 1841: Tibetisch-Deutsches Wörterbuch.\n"
            "Titel „Prajña-pāramitā-\n"
            "samcaya“ in bibliographischer Form.\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("Titel „Prajña-pāramitā-\nsamcaya“ in bibliographischer Form.", corrected)
        self.assertEqual(result["structural_rewrite_count"], 0)

    def test_structural_quote_wrap_direct_stays_on_immediate_next_line(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "beispiel „Würmer, Insekten und Fi-\n"
            "sche usw. sind aus Warmem und Feuchtem\n"
            "geboren (skt. svedaja)“\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("„Würmer, Insekten und Fische usw. sind aus Warmem und Feuchtem", corrected)
        self.assertIn("geboren (skt. svedaja)“", corrected)
        self.assertNotIn("Figeboren", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("Fi-/sche", "Fische", "structural_german_quote_hyphen_wrap_direct"),
            reasons,
        )

    def test_structural_quote_wrap_does_not_join_hyphenated_phrase(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Lex. „i.S.v. von Sonnen-\n"
            "und Schattenseite“.\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("„i.S.v. von Sonnen-\nund Schattenseite“.", corrected)
        self.assertNotIn("Sonnenund", corrected)
        self.assertEqual(result["structural_rewrite_count"], 0)


class LocCanonicalizationTests(unittest.TestCase):
    def test_loc_canonicalization_keeps_output_in_loc(self) -> None:
        self.assertEqual(pem.canonicalize_translit_token("byañ"), "byaṅ")
        self.assertEqual(pem.canonicalize_translit_token("gsañ"), "gsaṅ")
        self.assertEqual(pem.canonicalize_translit_token("kyañ"), "kyaṅ")
        self.assertEqual(pem.canonicalize_translit_token("yañ"), "yaṅ")

    def test_loc_name_piece_detection_is_diacritic_first(self) -> None:
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("śes"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("saṅs"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("lhun"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("byaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("gsaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("bzaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("dbaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("sangs"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("byang"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("gsang"))

    def test_hyphenated_initial_i_to_l_translit_accepts_loc_forms(self) -> None:
        self.assertTrue(pem.token_is_safe_hyphenated_initial_i_to_l_translit("Rigs-Idan", "Rigs-ldan"))
        self.assertTrue(
            pem.token_is_safe_hyphenated_initial_i_to_l_translit("Bkra-śis-Ihun-po", "Bkra-śis-lhun-po")
        )
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ita", "lta"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Iha", "lha"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ihan", "lhan"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ihun", "lhun"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Iho", "lho"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Itos", "ltos"))

    def test_distinctive_loc_clusters_detected_without_wylie_shadow(self) -> None:
        self.assertTrue(bool(pem.DISTINCTIVE_TIB_CLUSTER_RE.search("gźon")))
        self.assertTrue(bool(pem.DISTINCTIVE_TIB_CLUSTER_RE.search("sñiṅ")))

    def test_ascii_translit_evidence_restores_context_without_changing_loc_output(self) -> None:
        self.assertTrue(pem.token_has_translit_cue("byang"))
        self.assertTrue(pem.token_has_translit_cue("gsang"))
        self.assertTrue(pem.token_has_translit_cue("kyang"))
        self.assertTrue(pem.token_has_translit_cue("yang"))
        self.assertTrue(pem.token_has_translit_cue("kyis"))
        self.assertTrue(pem.token_has_translit_cue("gyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("byang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gsang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("yang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gyis"))

    def test_loc_short_syllables_restore_safe_ascii_translit_recall(self) -> None:
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyaṅ"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("byaṅ"))

    def test_token_is_translit_like_recovers_ascii_loc_contexts(self) -> None:
        self.assertTrue(pem.token_is_translit_like("byang", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("gsang", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("kyis", line_has_tibetan=True, is_entry_start=False))
        self.assertTrue(pem.token_is_translit_like("gyis", line_has_tibetan=True, is_entry_start=False))
        self.assertTrue(pem.token_is_translit_like("lhun", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("lta", line_has_tibetan=True, is_entry_start=False))

    def test_token_is_translit_like_rejects_plain_german_or_latin_words(self) -> None:
        self.assertFalse(pem.token_is_translit_like("einen", line_has_tibetan=False, is_entry_start=True))
        self.assertFalse(pem.token_is_translit_like("Wrightia", line_has_tibetan=False, is_entry_start=True))
        self.assertFalse(
            pem.token_is_translit_like("antidysenterica", line_has_tibetan=False, is_entry_start=False)
        )


if __name__ == "__main__":
    unittest.main()
