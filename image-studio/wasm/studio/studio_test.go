package main

import (
	"bytes"
	"encoding/json"
	"image"
	"image/color"
	"math"
	"strings"
	"testing"
)

const testLetters = "ABCEFGHIJMNOPQRTUVWXYZabcdefghijklmnopqrtuvwxyz"

func pngOf(t *testing.T, img image.Image) []byte {
	t.Helper()
	data, err := encodePNG(img)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

// hatWithGlowingBell draws a green block with a dark outline and a yellow
// bell surrounded by a soft glow that blends the bell colour into the
// magenta background, like the defect of the Go/WASM spike.
func hatWithGlowingBell(t *testing.T) []byte {
	t.Helper()
	bg := rgb{242, 14, 138}
	bell := rgb{249, 212, 72}
	img := image.NewNRGBA(image.Rect(0, 0, 512, 512))
	set := func(x, y int, c rgb) {
		img.SetNRGBA(x, y, color.NRGBA{clamp8(c.r), clamp8(c.g), clamp8(c.b), 255})
	}
	for y := 0; y < 512; y++ {
		for x := 0; x < 512; x++ {
			c := bg
			dx, dy := float64(x-400), float64(y-220)
			d := math.Hypot(dx, dy)
			switch {
			case x >= 96 && x < 352 && y >= 120 && y < 320:
				c = rgb{39, 148, 73}
				if x < 104 || x >= 344 || y < 128 || y >= 312 {
					c = rgb{27, 20, 48}
				}
			case d < 22:
				c = bell
			case d < 26:
				c = rgb{27, 20, 48}
			case d < 60:
				// Glow: from 55 % bell at the rim down to pure background.
				a := 0.55 * (60 - d) / 34
				c = rgb{bg.r + a*(bell.r-bg.r), bg.g + a*(bell.g-bg.g), bg.b + a*(bell.b-bg.b)}
			}
			set(x, y, c)
		}
	}
	return pngOf(t, img)
}

func gridOptions() GridOptions {
	return GridOptions{Box: Box{X: 4, Y: 0, W: 24, H: 12}, Size: 32, MaxColors: 10, Tolerance: 70, Outline: "#1b1430",
		Letters: testLetters, PreviewScale: 8}
}

func pinkish(hex string) bool {
	c := parseHex(hex)
	return c.R > 200 && c.B > 90 && c.G < 140
}

func TestDefringeRemovesGlow(t *testing.T) {
	src := hatWithGlowingBell(t)
	opt := gridOptions()
	art, _, _, err := PixelGrid(src, opt)
	if err != nil {
		t.Fatal(err)
	}
	glow := false
	for _, v := range art.Palette {
		glow = glow || pinkish(v)
	}
	if !glow {
		t.Fatalf("the synthetic glow should survive without defringe: %v", art.Palette)
	}
	opt.Defringe = true
	art, preview, st, err := PixelGrid(src, opt)
	if err != nil {
		t.Fatal(err)
	}
	for l, v := range art.Palette {
		if pinkish(v) {
			t.Fatalf("pink glow cell %s=%s survives defringe: %v", l, v, art.Palette)
		}
	}
	if st.ClearedPx == 0 || !bytes.HasPrefix(preview, []byte("\x89PNG")) {
		t.Fatalf("unexpected stats %+v", st)
	}
	yellow := false
	for _, v := range art.Palette {
		c := parseHex(v)
		yellow = yellow || (c.R > 200 && c.G > 170 && c.B < 120)
	}
	if !yellow {
		t.Fatalf("the bell disappeared: %v", art.Palette)
	}
}

func TestPixelGridRespectsGridContract(t *testing.T) {
	opt := gridOptions()
	opt.Defringe = true
	art, _, st, err := PixelGrid(hatWithGlowingBell(t), opt)
	if err != nil {
		t.Fatal(err)
	}
	if art.Palette["K"] != "#1b1430" || len(art.Palette) > 10 || st.Colors != len(art.Palette) {
		t.Fatalf("palette %v", art.Palette)
	}
	f := art.Frames[0]
	if f.Py < 0 || f.Py+len(f.Px) > 32 || f.Py+len(f.Px) > opt.Box.Y+opt.Box.H+1 {
		t.Fatalf("frame outside its box: py=%d rows=%d", f.Py, len(f.Px))
	}
	for _, row := range f.Px {
		if len(row) != 32 {
			t.Fatalf("row length %d", len(row))
		}
		for _, c := range row {
			if c != '.' && art.Palette[string(c)] == "" {
				t.Fatalf("letter %c is not in the palette", c)
			}
			if strings.ContainsRune("SsDL", c) {
				t.Fatalf("reserved letter %c used", c)
			}
		}
	}
	for _, v := range art.Palette {
		if !hexPattern.MatchString(v) {
			t.Fatalf("colour %q is not lowercase #rrggbb", v)
		}
	}
	close := renderArtCloseUp(art, 384).Bounds()
	if close.Dx() > 384+32 || close.Dy() > 384+32 || close.Dx() < 100 {
		t.Fatalf("close-up should frame the drawn cells at about 384 px: %v", close)
	}
}

func TestKeepTopUsesTheUpperPartOfTheSubject(t *testing.T) {
	// A tall block: top half red, bottom half blue, on magenta.
	img := image.NewNRGBA(image.Rect(0, 0, 200, 200))
	for y := 0; y < 200; y++ {
		for x := 0; x < 200; x++ {
			c := color.NRGBA{255, 0, 255, 255}
			if x >= 60 && x < 140 && y >= 20 && y < 180 {
				c = color.NRGBA{200, 30, 40, 255}
				if y >= 100 {
					c = color.NRGBA{30, 60, 200, 255}
				}
			}
			img.SetNRGBA(x, y, c)
		}
	}
	opt := gridOptions()
	opt.Box = Box{X: 4, Y: 22, W: 24, H: 10, KeepTop: 0.5}
	art, _, st, err := PixelGrid(pngOf(t, img), opt)
	if err != nil {
		t.Fatal(err)
	}
	for _, v := range art.Palette {
		if c := parseHex(v); c.B > 150 && c.R < 100 {
			t.Fatalf("the lower half should be cut: %v", art.Palette)
		}
	}
	if st.BoxFillRatio < 0.3 {
		t.Fatalf("the kept part should fill the wide box: %+v", st)
	}
}

func TestClearEnclosedRemovesBackgroundHoles(t *testing.T) {
	// A green ring with a magenta hole the border flood cannot reach.
	img := image.NewNRGBA(image.Rect(0, 0, 256, 256))
	for y := 0; y < 256; y++ {
		for x := 0; x < 256; x++ {
			c := color.NRGBA{255, 0, 255, 255}
			d := math.Hypot(float64(x-128), float64(y-128))
			if d < 90 && d >= 40 {
				c = color.NRGBA{40, 140, 70, 255}
			}
			img.SetNRGBA(x, y, c)
		}
	}
	opt := gridOptions()
	art, _, _, err := PixelGrid(pngOf(t, img), opt)
	if err != nil {
		t.Fatal(err)
	}
	hasMagenta := func(a Art) bool {
		for _, v := range a.Palette {
			if c := parseHex(v); c.R > 200 && c.B > 200 && c.G < 80 {
				return true
			}
		}
		return false
	}
	if !hasMagenta(art) {
		t.Fatalf("without clear_enclosed the hole stays: %v", art.Palette)
	}
	opt.ClearHoles = true
	art, _, _, err = PixelGrid(pngOf(t, img), opt)
	if err != nil {
		t.Fatal(err)
	}
	if hasMagenta(art) {
		t.Fatalf("clear_enclosed must clear the hole: %v", art.Palette)
	}
}

func TestProfileRefusesUnsafeOrIncompleteData(t *testing.T) {
	for _, mutate := range []func(*Profile){
		func(p *Profile) { p.Document.File = "../other/item.json" },
		func(p *Profile) { p.Document.File = ".." },
		func(p *Profile) { p.Export.File = "../banner.png" },
		func(p *Profile) { p.Planning.Attributes["rarity"] = nil },
		func(p *Profile) { p.Export.Letters = "KKKKKKKKKKKK" },
	} {
		p := testProfile(t)
		mutate(p)
		if err := p.Validate(); err == nil {
			t.Fatalf("profile should be refused: %+v %+v", p.Document, p.Export)
		}
	}
	p := testProfile(t)
	p.Document.Template = nil
	job := Job{Asset: Asset{ID: "hat_x", Attributes: map[string]string{"rarity": "rare"}}}
	if doc, err := BuildDocument(p.Document, job, nil); err != nil || doc["item_id"] != "hat_x" {
		t.Fatalf("a document without template still builds: %v %v", doc, err)
	}
}

func TestCloseUpStaysBoundedOnLargeGrids(t *testing.T) {
	row := strings.Repeat(".", 127) + "A"
	art := Art{Size: 128, Palette: map[string]string{"A": "#102030"}, Frames: []Frame{{Py: 0, Px: []string{row}}}}
	if b := renderArtCloseUp(art, 384).Bounds(); b.Dx() > 4096 || b.Dy() > 4096 {
		t.Fatalf("close-up too large: %v", b)
	}
}

func TestPixelGridRejectsUniformImage(t *testing.T) {
	img := image.NewNRGBA(image.Rect(0, 0, 16, 16))
	for i := range img.Pix {
		img.Pix[i] = 255
	}
	if _, _, _, err := PixelGrid(pngOf(t, img), gridOptions()); err == nil {
		t.Fatal("expected an error for an image without foreground")
	}
}

func TestRasterExportCoverAndContain(t *testing.T) {
	img := image.NewNRGBA(image.Rect(0, 0, 320, 180))
	for y := 0; y < 180; y++ {
		for x := 0; x < 320; x++ {
			img.SetNRGBA(x, y, color.NRGBA{uint8(x * 255 / 319), uint8(y * 255 / 179), 80, 255})
		}
	}
	src := pngOf(t, img)
	out, st, err := RasterExport(src, 160, 40, "cover")
	if err != nil {
		t.Fatal(err)
	}
	dec, _, err := image.Decode(bytes.NewReader(out))
	if err != nil || dec.Bounds().Dx() != 160 || dec.Bounds().Dy() != 40 {
		t.Fatalf("cover size %v %v", dec.Bounds(), err)
	}
	if st.Crop != [4]int{0, 50, 320, 80} {
		t.Fatalf("cover crop %v", st.Crop)
	}
	out, _, err = RasterExport(src, 100, 100, "contain")
	if err != nil {
		t.Fatal(err)
	}
	dec, _, _ = image.Decode(bytes.NewReader(out))
	if _, _, _, a := dec.At(50, 5).RGBA(); a != 0 {
		t.Fatal("contain should letterbox on transparency")
	}
	if _, _, _, a := dec.At(50, 50).RGBA(); a == 0 {
		t.Fatal("contain lost the image")
	}
}

func TestReviewSheetLayout(t *testing.T) {
	tile := pngOf(t, image.NewNRGBA(image.Rect(0, 0, 8, 8)))
	sheet, err := ReviewSheet([]SheetTile{{PNG: tile, Status: "accepted"}, {Status: "needs_review"}, {PNG: tile, Status: "failed"}}, 64, 2)
	if err != nil {
		t.Fatal(err)
	}
	img, _, err := image.Decode(bytes.NewReader(sheet))
	if err != nil {
		t.Fatal(err)
	}
	if w, h := img.Bounds().Dx(), img.Bounds().Dy(); w != 2*(64+12)+12 || h != 2*(64+8+12)+12 {
		t.Fatalf("sheet size %dx%d", w, h)
	}
	if r, g, _, _ := img.At(12+64+12+1, 12+64+1).RGBA(); !(r>>8 > 200 && g>>8 > 140) {
		t.Fatal("second tile should carry the amber needs-review band")
	}
}

func testProfile(t *testing.T) *Profile {
	t.Helper()
	p, err := ParseProfile([]byte(`{
	  "schema": "image-studio.profile/v1", "key": "test-grid", "title": "Test",
	  "planning": {"max_assets": 3, "id_pattern": "^[a-z0-9_]{1,32}$",
	    "categories": [{"key": "hat", "id_prefix": "hat_", "framing": "wider than tall", "review": "Judge the hat alone."}, {"key": "accessory", "id_prefix": "acc_", "placements": ["neck", "face"]}],
	    "attributes": {"rarity": ["common", "rare"]}},
	  "generation": {"aspect_ratio": "1:1", "style_prefix": "Pixel sprite.", "background": "Flat magenta background."},
	  "export": {"kind": "pixel-grid", "size": 32, "max_colors": 10, "outline": "#1b1430", "letters": "` + testLetters + `",
	    "boxes": {"hat": {"x": 4, "y": 0, "w": 24, "h": 12}, "accessory": {"x": 6, "y": 13, "w": 20, "h": 9},
	      "accessory:neck": {"x": 7, "y": 20, "w": 18, "h": 7}, "accessory:face": {"x": 6, "y": 10, "w": 20, "h": 6}}},
	  "judge": {"prompt": "Review.", "min_score": 6, "min_opaque_cells": 40},
	  "document": {"file": "item.json", "template": {"kind": "avatar_item", "author": {"name": "Test"}},
	    "fields": {"item_id": "asset.id", "slot": "asset.category", "rarity": "asset.attributes.rarity", "theme": "pack.theme", "art": "export.art"},
	    "by_attribute": {"rarity": {"common": {"audiences": ["kids"]}, "rare": {"audiences": ["adults"]}}}},
	  "pricing": {"attribute": "rarity", "unit": "R", "values": {"common": 0, "rare": 200}}
	}`))
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func TestProfileValidation(t *testing.T) {
	p := testProfile(t)
	p.Export.Boxes = map[string]Box{"hat": {X: 30, Y: 0, W: 8, H: 4}}
	err := p.Validate()
	if err == nil || !strings.Contains(err.Error(), "outside the grid") || !strings.Contains(err.Error(), "accessory:neck") {
		t.Fatalf("expected box errors, got %v", err)
	}
	if _, err := ParseProfile([]byte(`{"schema": "image-studio.profile/v1", "unknown": 1}`)); err == nil {
		t.Fatal("unknown fields must be refused")
	}
}

func TestNormalizePlanRepairsDraft(t *testing.T) {
	p := testProfile(t)
	d := PlanDraft{Title: "Winter", Assets: []Asset{
		{ID: "Elf Hat", Title: "Elf hat", Category: "HAT", Subject: "green elf hat", Attributes: map[string]string{"rarity": "rare"}},
		{ID: "elf_hat", Title: "Elf hat again", Category: "hat", Subject: "another hat"},
		{ID: "scarf", Title: "Scarf", Category: "accessory", Placement: "waist", Subject: "red scarf"},
		{ID: "boots", Category: "feet", Subject: "boots"},
		{ID: "bell", Category: "hat", Subject: "bell hat"},
	}}
	plan, err := NormalizePlan(p, d, "brief", "noel-2026", "noel-2026", 10)
	if err != nil {
		t.Fatal(err)
	}
	ids := []string{}
	for _, a := range plan.Assets {
		ids = append(ids, a.ID)
	}
	if strings.Join(ids, ",") != "hat_elf_hat,hat_elf_hat_2,acc_scarf" {
		t.Fatalf("ids %v", ids)
	}
	if plan.Assets[2].Placement != "neck" || plan.Assets[1].Attributes["rarity"] != "common" {
		t.Fatalf("repairs %+v", plan.Assets)
	}
	if len(plan.Issues) < 4 {
		t.Fatalf("every repair must be reported: %v", plan.Issues)
	}
	if _, err := NormalizePlan(p, d, "brief", "Bad Pack", "x", 3); err == nil {
		t.Fatal("invalid pack ids must be refused")
	}
}

func TestStyleSheetJobsAndDocument(t *testing.T) {
	p := testProfile(t)
	plan, err := NormalizePlan(p, PlanDraft{ArtDirection: ArtDirection{Summary: "cosy winter", Palette: []string{"forest green", "gold"},
		Rules: []string{"thick outline"}}, Assets: []Asset{
		{ID: "hat_elf", Title: "Elf hat", Category: "hat", Subject: "green elf hat", Attributes: map[string]string{"rarity": "rare"}},
		{ID: "acc_scarf", Title: "Scarf", Category: "accessory", Placement: "neck", Subject: "red scarf"},
	}}, "brief", "noel-2026", "noel-2026", 0)
	if err != nil {
		t.Fatal(err)
	}
	sheet, jobs := BuildStyleSheet(p, plan, "/image-studio/packs")
	if len(jobs) != 2 || !strings.Contains(sheet.Prefix, "forest green, gold") {
		t.Fatalf("sheet %+v", sheet)
	}
	j := jobs[1]
	if j.Dir != "/image-studio/packs/noel-2026/acc_scarf" || j.BoxKey != "accessory:neck" || len(j.Export.Boxes) != 1 {
		t.Fatalf("job %+v", j)
	}
	if !strings.Contains(jobs[0].Prompt, "Framing: wider than tall.") || strings.Contains(jobs[1].Prompt, "Framing") {
		t.Fatalf("framing belongs to its category: %q / %q", jobs[0].Prompt, jobs[1].Prompt)
	}
	if !strings.Contains(jobs[0].JudgePrompt, "Judge the hat alone.") || strings.Contains(jobs[1].JudgePrompt, "hat alone") {
		t.Fatalf("review notes belong to their category: %q", jobs[0].JudgePrompt)
	}
	for _, job := range jobs {
		if !strings.HasPrefix(job.Prompt, sheet.Prefix) || !strings.Contains(job.Prompt, "thick outline") {
			t.Fatalf("every prompt shares the style sheet: %q", job.Prompt)
		}
	}
	if jobs[0].Price == nil || jobs[0].Price.Value != 200 || jobs[1].Price.Value != 0 {
		t.Fatalf("prices %+v %+v", jobs[0].Price, jobs[1].Price)
	}
	doc, err := BuildDocument(p.Document, jobs[0], map[string]any{"size": 32})
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(doc)
	want := `{"art":{"size":32},"audiences":["adults"],"author":{"name":"Test"},"item_id":"hat_elf","kind":"avatar_item","rarity":"rare","slot":"hat","theme":"noel-2026"}`
	if string(raw) != want {
		t.Fatalf("document\n got %s\nwant %s", raw, want)
	}
}

func TestReviewParsingAndDecision(t *testing.T) {
	job := Job{Export: ExportConfig{Kind: "pixel-grid"}, Judge: JudgeConfig{MinScore: 6, MinOpaqueCell: 40}, Prompt: "p"}
	tool := map[string]any{"outputs": []any{map[string]any{"text": "Sure:\n```json\n{\"score\": 8, \"pass\": true, \"issues\": []}\n```"}}}
	r := ParseReview(tool)
	if !r.Available || r.Score != 8 || !r.Pass {
		t.Fatalf("review %+v", r)
	}
	good := map[string]any{"opaque_cells": 120.0, "box_fill_ratio": 0.6}
	if v := Decide(job, good, r, 1, false); v.Next != "accept" || v.Status != "accepted" {
		t.Fatalf("verdict %+v", v)
	}
	small := map[string]any{"opaque_cells": 12.0}
	v := Decide(job, small, r, 1, false)
	if v.Next != "retry" || len(v.Checks) != 1 || !strings.Contains(RetryPrompt(job, v), "opaque cells") {
		t.Fatalf("verdict %+v", v)
	}
	if v := Decide(job, small, r, 2, true); v.Next != "accept" || v.Status != "needs_review" {
		t.Fatalf("final verdict %+v", v)
	}
	if r := ParseReview(map[string]any{"text": `the score is {"pass": true}`}); r.Available {
		t.Fatalf("a JSON object without score is not a review: %+v", r)
	}
	if v := Decide(job, good, ParseReview(map[string]any{"text": "no json"}), 2, true); v.Status != "needs_review" {
		t.Fatalf("an unreadable review is never an acceptance: %+v", v)
	}
}

func TestFindRecordsKeepsPlanOrder(t *testing.T) {
	nested := []any{
		map[string]any{"outcome": map[string]any{"asset": map[string]any{"record": AssetRecord, "index": 1.0, "dir": "/b"}}},
		map[string]any{"asset": map[string]any{"record": AssetRecord, "index": 0.0, "dir": "/a"}},
		`{"record": "image-studio.asset/v1", "index": 2, "dir": "/c"}`,
		map[string]any{"again": map[string]any{"record": AssetRecord, "index": 0.0, "dir": "/a"}},
	}
	nested = append(nested, map[string]any{"asset": map[string]any{"record": HeldRecord, "index": 3.0, "id": "hat_held", "dir": "/d"}})
	recs := findRecords(nested)
	if len(recs) != 4 || recs[3]["id"] != "hat_held" || recs[0]["dir"] != "/a" || recs[2]["dir"] != "/c" {
		t.Fatalf("records %v", recs)
	}
}

func TestInputUnwrapping(t *testing.T) {
	var job Job
	if err := decode(json.RawMessage(`"{\"pack_id\": \"p\"}"`), &job); err != nil || job.PackID != "p" {
		t.Fatalf("templated object: %v %+v", err, job)
	}
	if num(json.RawMessage(`"12"`), 3) != 12 || num(json.RawMessage(`null`), 3) != 3 {
		t.Fatal("num")
	}
	for _, p := range []string{"relative", "/a/../b", "/a\\b"} {
		if _, err := cleanPath(p); err == nil {
			t.Fatalf("path %q must be refused", p)
		}
	}
}
