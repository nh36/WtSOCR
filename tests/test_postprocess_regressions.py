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
