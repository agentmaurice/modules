// Command studio is the Go/WASM action of the image-studio Module. One
// binary serves every code step of its Workflows, selected by "op": profile
// loading, plan normalization, style sheet, export of an attempt, verdict,
// finalization, publication and review reading. It only uses existing tools
// (read_file, write_file) and the buffers returned by the image tool.
package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path"
	"runtime/debug"
	"strings"

	"github.com/agentmaurice/chatserver/pkg/workflow"
)

// AssetRecord marks the final record of one asset; publish looks for it.
const AssetRecord = "image-studio.asset/v1"

// HeldRecord marks an asset that the decision fallback held without files.
const HeldRecord = "image-studio.held/v1"

// FileEntry is one written file of the manifest.
type FileEntry struct {
	Path   string `json:"path"`
	Role   string `json:"role"`
	SHA256 string `json:"sha256"`
	Bytes  int    `json:"bytes"`
}

type studio struct{ s *workflow.Script }

func main() {
	// The WASM heap never shrinks: collect early so decoding a large image
	// stays far below the worker memory limit.
	debug.SetGCPercent(25)
	if err := workflow.RunScript(os.Stdin, os.Stdout, run); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func run(s *workflow.Script) error {
	var in map[string]json.RawMessage
	if err := json.Unmarshal(s.Input(), &in); err != nil {
		return fmt.Errorf("invalid input: %w", err)
	}
	st := studio{s}
	ops := map[string]func(map[string]json.RawMessage) (any, error){
		"prepare_plan": st.preparePlan, "plan": st.plan, "style_sheet": st.styleSheet, "single_job": st.singleJob,
		"attempt": st.attempt, "verdict": st.verdict, "finalize": st.finalize, "publish": st.publish,
		"export": st.export, "save_profile": st.saveProfile, "read_review": st.readReview,
	}
	op := str(in["op"])
	fn, ok := ops[op]
	if !ok {
		return fmt.Errorf("unknown op %q", op)
	}
	out, err := fn(in)
	if err != nil {
		return fmt.Errorf("%s: %w", op, err)
	}
	return s.Result(out)
}

// --- input helpers -------------------------------------------------------

// unwrap accepts a value as JSON or as a JSON document templated into a
// string, which is how a Workflow may pass an object through context.
func unwrap(raw json.RawMessage) json.RawMessage {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		t := strings.TrimSpace(s)
		if strings.HasPrefix(t, "{") || strings.HasPrefix(t, "[") {
			return json.RawMessage(t)
		}
	}
	return raw
}

func decode(raw json.RawMessage, v any) error {
	if len(raw) == 0 || string(raw) == "null" {
		return errors.New("missing value")
	}
	return json.Unmarshal(unwrap(raw), v)
}

func str(raw json.RawMessage) string {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return strings.TrimSpace(s)
	}
	return strings.Trim(strings.TrimSpace(string(raw)), `"`)
}

func num(raw json.RawMessage, def int) int {
	var n float64
	if json.Unmarshal(unwrap(raw), &n) == nil && n > 0 {
		return int(n)
	}
	var s string
	if json.Unmarshal(raw, &s) == nil {
		var m int
		if _, err := fmt.Sscanf(strings.TrimSpace(s), "%d", &m); err == nil && m > 0 {
			return m
		}
	}
	return def
}

// DefaultRoot is the Storage folder of the packs when the caller gives none.
const DefaultRoot = "/image-studio/packs"

func rootOf(in map[string]json.RawMessage) (string, error) {
	if r := str(in["root"]); r != "" {
		return cleanPath(r)
	}
	return DefaultRoot, nil
}

// themeOf defaults the theme to the pack id.
func themeOf(in map[string]json.RawMessage) string {
	if t := str(in["theme"]); t != "" {
		return t
	}
	return str(in["pack_id"])
}

func cleanPath(p string) (string, error) {
	if !strings.HasPrefix(p, "/") || strings.Contains(p, "..") || strings.ContainsAny(p, "\\\x00") {
		return "", fmt.Errorf("invalid Storage path %q", p)
	}
	return path.Clean(p), nil
}

// --- Storage -------------------------------------------------------------

func (st studio) readFile(p string) ([]byte, error) {
	out, err := st.s.CallTool("read_file", map[string]any{"path": p, "encoding": "base64"})
	if err != nil {
		return nil, fmt.Errorf("read_file %s: %w", p, err)
	}
	m, _ := out.(map[string]any)
	if c, _ := m["content"].(string); c != "" {
		return base64.StdEncoding.DecodeString(c)
	}
	if ref, _ := m["buffer_ref"].(string); ref != "" {
		return st.loadBuffer(ref)
	}
	return nil, fmt.Errorf("read_file %s returned no content", p)
}

func (st studio) loadBuffer(ref string) ([]byte, error) {
	v, err := st.s.BufferLoad(strings.TrimPrefix(ref, "buffer://"))
	if err != nil {
		return nil, fmt.Errorf("buffer_load: %w", err)
	}
	text := v.Text
	switch c := v.Content.(type) {
	case string:
		text = c
	case map[string]any:
		for _, k := range []string{"data", "content", "base64"} {
			if s, _ := c[k].(string); s != "" {
				text = s
				break
			}
		}
	}
	if i := strings.Index(text, ";base64,"); strings.HasPrefix(text, "data:") && i > 0 {
		text = text[i+len(";base64,"):]
	}
	if text == "" {
		return nil, errors.New("buffer has no content")
	}
	return base64.StdEncoding.DecodeString(text)
}

func (st studio) writeFile(p, role string, data []byte) (FileEntry, error) {
	if _, err := st.s.CallTool("write_file", map[string]any{"path": p, "content": base64.StdEncoding.EncodeToString(data),
		"encoding": "base64", "overwrite": true}); err != nil {
		return FileEntry{}, fmt.Errorf("write_file %s: %w", p, err)
	}
	return entry(p, role, data), nil
}

func (st studio) writeJSON(p, role string, v any) (FileEntry, error) {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return FileEntry{}, err
	}
	return st.writeFile(p, role, append(data, '\n'))
}

func entry(p, role string, data []byte) FileEntry {
	sum := sha256.Sum256(data)
	return FileEntry{Path: p, Role: role, SHA256: hex.EncodeToString(sum[:]), Bytes: len(data)}
}

func (st studio) loadProfile(p string) (*Profile, error) {
	p, err := cleanPath(p)
	if err != nil {
		return nil, err
	}
	raw, err := st.readFile(p)
	if err != nil {
		return nil, err
	}
	return ParseProfile(raw)
}

// --- ops -----------------------------------------------------------------

// preparePlan loads the profile and composes the planner prompt.
func (st studio) preparePlan(in map[string]json.RawMessage) (any, error) {
	p, err := st.loadProfile(str(in["profile_path"]))
	if err != nil {
		return nil, err
	}
	brief := str(in["brief"])
	if brief == "" {
		return nil, errors.New("brief is empty")
	}
	maxAssets := min(num(in["max_assets"], p.Planning.MaxAssets), p.Planning.MaxAssets)
	return map[string]any{"profile": p, "planner_prompt": PlannerPrompt(p, brief, maxAssets), "max_assets": maxAssets}, nil
}

// plan normalizes the planner draft and stores plan.json.
func (st studio) plan(in map[string]json.RawMessage) (any, error) {
	var p Profile
	if err := decode(in["profile"], &p); err != nil {
		return nil, fmt.Errorf("profile: %w", err)
	}
	if err := p.Validate(); err != nil {
		return nil, err
	}
	d, err := ParseDraft(unwrap(in["draft"]))
	if err != nil {
		return nil, err
	}
	root, err := rootOf(in)
	if err != nil {
		return nil, err
	}
	plan, err := NormalizePlan(&p, d, str(in["brief"]), str(in["pack_id"]), themeOf(in), num(in["max_assets"], 0))
	if err != nil {
		return nil, err
	}
	f, err := st.writeJSON(root+"/"+plan.PackID+"/plan.json", "plan", plan)
	if err != nil {
		return nil, err
	}
	return map[string]any{"plan": plan, "file": f}, nil
}

// styleSheet stores style.json and returns one self-contained job per asset.
func (st studio) styleSheet(in map[string]json.RawMessage) (any, error) {
	var p Profile
	if err := decode(in["profile"], &p); err != nil {
		return nil, fmt.Errorf("profile: %w", err)
	}
	if err := p.Validate(); err != nil {
		return nil, err
	}
	var plan Plan
	if err := decode(in["plan"], &plan); err != nil {
		return nil, fmt.Errorf("plan: %w", err)
	}
	root, err := rootOf(in)
	if err != nil {
		return nil, err
	}
	sheet, jobs := BuildStyleSheet(&p, plan, root)
	f, err := st.writeJSON(root+"/"+plan.PackID+"/style.json", "style", sheet)
	if err != nil {
		return nil, err
	}
	return map[string]any{"style": sheet, "jobs": jobs, "file": f}, nil
}

// singleJob plans one asset directly from a brief (render Workflow).
func (st studio) singleJob(in map[string]json.RawMessage) (any, error) {
	p, err := st.loadProfile(str(in["profile_path"]))
	if err != nil {
		return nil, err
	}
	root, err := rootOf(in)
	if err != nil {
		return nil, err
	}
	category := str(in["category"])
	if category == "" {
		category = p.Planning.Categories[0].Key
	}
	draft := PlanDraft{Title: str(in["title"]), Assets: []Asset{{ID: str(in["asset_id"]), Title: str(in["title"]),
		Category: category, Placement: str(in["placement"]), Subject: str(in["brief"])}}}
	plan, err := NormalizePlan(p, draft, str(in["brief"]), str(in["pack_id"]), themeOf(in), 1)
	if err != nil {
		return nil, err
	}
	_, jobs := BuildStyleSheet(p, plan, root)
	return map[string]any{"job": jobs[0], "plan": plan}, nil
}

// attempt stores the generated image, exports it with the job profile and
// returns the review material. Nothing here decides acceptance.
func (st studio) attempt(in map[string]json.RawMessage) (any, error) {
	var job Job
	if err := decode(in["job"], &job); err != nil {
		return nil, fmt.Errorf("job: %w", err)
	}
	n := num(in["attempt"], 1)
	var gen any
	if err := decode(in["generated"], &gen); err != nil {
		return nil, fmt.Errorf("generated: %w", err)
	}
	var refs []string
	findBufferRefs(gen, &refs)
	if len(refs) == 0 {
		return nil, errors.New("the image tool returned no buffer:// image")
	}
	dir, err := cleanPath(fmt.Sprintf("%s/attempt-%d", job.Dir, n))
	if err != nil {
		return nil, err
	}
	// The buffer expires after an hour: the source is stored first. It came
	// from a Workflow tool call, so the action reads it back from Storage
	// through its own call instead of loading the foreign buffer.
	if _, err := st.s.CallTool("write_file", map[string]any{"path": dir + "/source.png", "buffer_ref": refs[0], "overwrite": true}); err != nil {
		return nil, fmt.Errorf("write_file source: %w", err)
	}
	src, err := st.readFile(dir + "/source.png")
	if err != nil {
		return nil, err
	}
	files := []FileEntry{entry(dir+"/source.png", "source", src)}
	res, err := exportImage(job, src)
	if err != nil {
		return nil, err
	}
	f, err := st.writeFile(dir+"/"+res.File, res.Role, res.Output)
	if err != nil {
		return nil, err
	}
	files = append(files, f)
	return map[string]any{"attempt": n, "dir": dir, "files": files, "stats": res.Stats, "art": res.Art,
		"output_file": res.File, "judge_image": base64.StdEncoding.EncodeToString(res.JudgeImage)}, nil
}

type exportResult struct {
	File, Role string
	Output     []byte
	JudgeImage []byte
	Art        any
	Stats      any
}

func exportImage(job Job, src []byte) (exportResult, error) {
	switch job.Export.Kind {
	case "pixel-grid":
		opt, err := GridOptionsFor(job.Export, job.BoxKey)
		if err != nil {
			return exportResult{}, err
		}
		art, preview, stats, err := PixelGrid(src, opt)
		if err != nil {
			return exportResult{}, err
		}
		judge, err := encodePNG(renderArtCloseUp(art, 384))
		if err != nil {
			return exportResult{}, err
		}
		return exportResult{File: "preview.png", Role: "preview", Output: preview, JudgeImage: judge, Art: art, Stats: stats}, nil
	case "raster":
		out, stats, err := RasterExport(src, job.Export.Width, job.Export.Height, job.Export.Fit)
		if err != nil {
			return exportResult{}, err
		}
		thumb, err := Thumbnail(out, 768)
		if err != nil {
			return exportResult{}, err
		}
		file := job.Export.File
		if file == "" {
			file = "image.png"
		}
		return exportResult{File: file, Role: "image", Output: out, JudgeImage: thumb, Stats: stats}, nil
	}
	return exportResult{}, fmt.Errorf("unknown export kind %q", job.Export.Kind)
}

// verdict parses the vision review and decides accept or retry.
func (st studio) verdict(in map[string]json.RawMessage) (any, error) {
	var job Job
	if err := decode(in["job"], &job); err != nil {
		return nil, fmt.Errorf("job: %w", err)
	}
	var att struct {
		Attempt int            `json:"attempt"`
		Stats   map[string]any `json:"stats"`
	}
	if err := decode(in["attempt"], &att); err != nil {
		return nil, fmt.Errorf("attempt: %w", err)
	}
	var review any
	_ = decode(in["review"], &review)
	final := str(in["final"]) == "true"
	v := Decide(job, att.Stats, ParseReview(review), att.Attempt, final)
	return map[string]any{"verdict": v, "next": v.Next, "retry_prompt": RetryPrompt(job, v)}, nil
}

// finalize writes the kept attempt as the asset: the exported file, its
// document, and a record carrying every file hash.
func (st studio) finalize(in map[string]json.RawMessage) (any, error) {
	var job Job
	if err := decode(in["job"], &job); err != nil {
		return nil, fmt.Errorf("job: %w", err)
	}
	var att struct {
		Attempt    int             `json:"attempt"`
		Files      []FileEntry     `json:"files"`
		Art        json.RawMessage `json:"art"`
		Stats      map[string]any  `json:"stats"`
		OutputFile string          `json:"output_file"`
		Dir        string          `json:"dir"`
	}
	if err := decode(in["attempt"], &att); err != nil {
		return nil, fmt.Errorf("attempt: %w", err)
	}
	var vd struct {
		Verdict Verdict `json:"verdict"`
	}
	if err := decode(in["verdict"], &vd); err != nil {
		return nil, fmt.Errorf("verdict: %w", err)
	}
	dir, err := cleanPath(job.Dir)
	if err != nil {
		return nil, err
	}
	files := []FileEntry{}
	for _, f := range att.Files {
		if f.Role == "source" {
			files = append(files, f)
		}
	}
	out, err := st.readFile(att.Dir + "/" + att.OutputFile)
	if err != nil {
		return nil, err
	}
	role := "image"
	if job.Export.Kind == "pixel-grid" {
		role = "preview"
	}
	f, err := st.writeFile(dir+"/"+att.OutputFile, role, out)
	if err != nil {
		return nil, err
	}
	files = append(files, f)
	if job.Document != nil {
		var art any
		_ = json.Unmarshal(att.Art, &art)
		doc, err := BuildDocument(job.Document, job, art)
		if err != nil {
			return nil, err
		}
		f, err := st.writeJSON(dir+"/"+job.Document.File, "document", doc)
		if err != nil {
			return nil, err
		}
		files = append(files, f)
	}
	return map[string]any{"record": AssetRecord, "index": job.Index, "pack_id": job.PackID, "asset": job.Asset,
		"status": vd.Verdict.Status, "score": vd.Verdict.Score, "issues": append(vd.Verdict.Issues, vd.Verdict.Checks...),
		"attempts": att.Attempt, "kept_attempt": att.Dir, "dir": dir, "files": files, "stats": att.Stats,
		"price": job.Price, "profile": job.Profile}, nil
}

// publish writes the SHA-256 manifest, the review sheet and review.json.
func (st studio) publish(in map[string]json.RawMessage) (any, error) {
	var raw any
	_ = decode(in["assets"], &raw)
	records := findRecords(raw)
	if len(records) == 0 {
		return nil, errors.New("no asset record to publish")
	}
	root, err := rootOf(in)
	if err != nil {
		return nil, err
	}
	packID := str(in["pack_id"])
	if !packIDPattern.MatchString(packID) {
		return nil, fmt.Errorf("invalid pack_id %q", packID)
	}
	dir := root + "/" + packID
	var tiles []SheetTile
	var files []FileEntry
	counts := map[string]int{}
	var assets []map[string]any
	for _, r := range records {
		status, _ := r["status"].(string)
		counts[status]++
		var recFiles []FileEntry
		raw, _ := json.Marshal(r["files"])
		_ = json.Unmarshal(raw, &recFiles)
		files = append(files, recFiles...)
		tile := SheetTile{Status: status}
		for _, f := range recFiles {
			if f.Role == "preview" || f.Role == "image" {
				if data, err := st.readFile(f.Path); err == nil {
					if thumb, err := Thumbnail(data, 256); err == nil {
						tile.PNG = thumb
					}
				}
			}
		}
		tiles = append(tiles, tile)
		a, _ := r["asset"].(map[string]any)
		if a == nil {
			a = map[string]any{"id": r["id"]}
		}
		assets = append(assets, map[string]any{"index": len(assets), "id": a["id"], "title": a["title"], "category": a["category"],
			"placement": a["placement"], "attributes": a["attributes"], "status": status, "score": r["score"],
			"issues": r["issues"], "attempts": r["attempts"], "price": r["price"], "dir": r["dir"]})
	}
	sheet, err := ReviewSheet(tiles, 256, 5)
	if err != nil {
		return nil, err
	}
	sheetEntry, err := st.writeFile(dir+"/review-sheet.png", "review_sheet", sheet)
	if err != nil {
		return nil, err
	}
	manifest := map[string]any{"schema": "image-studio.manifest/v1", "pack_id": packID, "title": str(in["title"]),
		"profile": str(in["profile"]), "generated_by": "AgentMaurice image-studio", "assets": assets,
		"counts": counts, "files": files, "review_sheet": sheetEntry,
		"review": "The sheet shows the assets in manifest order, five per row; the band under each tile is its status " +
			"(green accepted, amber needs review). Publishing or selling stays a human decision outside this module."}
	mf, err := st.writeJSON(dir+"/manifest.json", "manifest", manifest)
	if err != nil {
		return nil, err
	}
	review := map[string]any{"schema": "image-studio.review/v1", "pack_id": packID, "title": str(in["title"]),
		"assets": assets, "counts": counts, "manifest": mf.Path, "manifest_sha256": mf.SHA256, "review_sheet": sheetEntry.Path}
	if _, err := st.writeJSON(dir+"/review.json", "review", review); err != nil {
		return nil, err
	}
	return map[string]any{"pack_id": packID, "manifest_path": mf.Path, "manifest_sha256": mf.SHA256,
		"review_sheet_path": sheetEntry.Path, "assets": len(records), "counts": counts, "files": len(files)}, nil
}

func findRecords(v any) []map[string]any {
	var out []map[string]any
	seen := map[string]bool{}
	var walk func(any)
	walk = func(v any) {
		switch t := v.(type) {
		case map[string]any:
			if t["record"] == AssetRecord || t["record"] == HeldRecord {
				key := fmt.Sprint(t["dir"], t["id"])
				if !seen[key] {
					seen[key] = true
					out = append(out, t)
				}
				return
			}
			for _, k := range sortedKeys(t) {
				walk(t[k])
			}
		case []any:
			for _, x := range t {
				walk(x)
			}
		case string:
			s := strings.TrimSpace(t)
			if strings.HasPrefix(s, "{") || strings.HasPrefix(s, "[") {
				var inner any
				if json.Unmarshal([]byte(s), &inner) == nil {
					walk(inner)
				}
			}
		}
	}
	walk(v)
	// Keep the plan order.
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && intOf(out[j]["index"]) < intOf(out[j-1]["index"]); j-- {
			out[j], out[j-1] = out[j-1], out[j]
		}
	}
	return out
}

// export re-exports a stored source with a profile, without generation.
func (st studio) export(in map[string]json.RawMessage) (any, error) {
	p, err := st.loadProfile(str(in["profile_path"]))
	if err != nil {
		return nil, err
	}
	srcPath, err := cleanPath(str(in["source_path"]))
	if err != nil {
		return nil, err
	}
	outDir, err := cleanPath(str(in["out_dir"]))
	if err != nil {
		return nil, err
	}
	src, err := st.readFile(srcPath)
	if err != nil {
		return nil, err
	}
	job := Job{Export: p.Export, Asset: Asset{Category: str(in["category"]), Placement: str(in["placement"])}}
	if job.Asset.Category == "" {
		job.Asset.Category = p.Planning.Categories[0].Key
	}
	job.BoxKey = job.Asset.Category
	if job.Asset.Placement != "" {
		job.BoxKey += ":" + job.Asset.Placement
	}
	res, err := exportImage(job, src)
	if err != nil {
		return nil, err
	}
	f, err := st.writeFile(outDir+"/"+res.File, res.Role, res.Output)
	if err != nil {
		return nil, err
	}
	return map[string]any{"file": f, "art": res.Art, "stats": res.Stats, "source": entry(srcPath, "source", src)}, nil
}

// saveProfile validates a profile document and stores it.
func (st studio) saveProfile(in map[string]json.RawMessage) (any, error) {
	raw := unwrap(in["profile"])
	p, err := ParseProfile(raw)
	if err != nil {
		return nil, err
	}
	target, err := cleanPath(str(in["path"]))
	if err != nil {
		return nil, err
	}
	f, err := st.writeJSON(target, "profile", p)
	if err != nil {
		return nil, err
	}
	return map[string]any{"key": p.Key, "kind": p.Export.Kind, "file": f}, nil
}

// readReview returns review.json of a pack for the review MiniApp.
func (st studio) readReview(in map[string]json.RawMessage) (any, error) {
	root, err := rootOf(in)
	if err != nil {
		return nil, err
	}
	packID := str(in["pack_id"])
	if !packIDPattern.MatchString(packID) {
		return nil, fmt.Errorf("invalid pack_id %q", packID)
	}
	data, err := st.readFile(root + "/" + packID + "/review.json")
	if err != nil {
		return nil, err
	}
	var review any
	if err := json.Unmarshal(data, &review); err != nil {
		return nil, err
	}
	return review, nil
}

// findBufferRefs collects every buffer:// reference of a tool result.
func findBufferRefs(v any, out *[]string) {
	switch t := v.(type) {
	case string:
		if strings.HasPrefix(t, "buffer://") {
			*out = append(*out, t)
		}
	case map[string]any:
		for _, k := range sortedKeys(t) {
			findBufferRefs(t[k], out)
		}
	case []any:
		for _, x := range t {
			findBufferRefs(x, out)
		}
	}
}
