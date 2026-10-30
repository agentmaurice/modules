package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// Asset is one planned image, independent of any output target.
type Asset struct {
	ID         string            `json:"id"`
	Title      string            `json:"title"`
	Category   string            `json:"category"`
	Placement  string            `json:"placement,omitempty"`
	Subject    string            `json:"subject"`
	Attributes map[string]string `json:"attributes,omitempty"`
}

// ArtDirection is the shared look of a pack.
type ArtDirection struct {
	Summary string   `json:"summary"`
	Palette []string `json:"palette"`
	Mood    string   `json:"mood"`
	Rules   []string `json:"rules"`
}

// Plan is the normalized result of the planning step.
type Plan struct {
	Schema       string       `json:"schema"`
	PackID       string       `json:"pack_id"`
	Title        string       `json:"title"`
	Theme        string       `json:"theme"`
	Brief        string       `json:"brief"`
	Profile      string       `json:"profile"`
	ArtDirection ArtDirection `json:"art_direction"`
	Assets       []Asset      `json:"assets"`
	Issues       []string     `json:"issues"`
}

// PlanDraft is what the planner model returns (see the planner schema).
type PlanDraft struct {
	Title        string       `json:"title"`
	ArtDirection ArtDirection `json:"art_direction"`
	Assets       []Asset      `json:"assets"`
}

var (
	packIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,47}$`)
	slugReplacer  = regexp.MustCompile(`[^a-z0-9_]+`)
)

// PlannerPrompt composes the instruction given to the planning model.
func PlannerPrompt(p *Profile, brief string, maxAssets int) string {
	var b strings.Builder
	fmt.Fprintf(&b, "You plan a coherent set of images for the output profile %q (%s).\n\n", p.Key, p.Title)
	fmt.Fprintf(&b, "Brief:\n%s\n\n", strings.TrimSpace(brief))
	if p.Planning.Guidance != "" {
		fmt.Fprintf(&b, "Profile guidance:\n%s\n\n", strings.TrimSpace(p.Planning.Guidance))
	}
	b.WriteString("Allowed categories:\n")
	for _, c := range p.Planning.Categories {
		fmt.Fprintf(&b, "- %s", c.Key)
		if c.Description != "" {
			fmt.Fprintf(&b, ": %s", c.Description)
		}
		if len(c.Placements) > 0 {
			fmt.Fprintf(&b, " (placement one of: %s)", strings.Join(c.Placements, ", "))
		}
		if c.IDPrefix != "" {
			fmt.Fprintf(&b, " (id starts with %q)", c.IDPrefix)
		}
		b.WriteString("\n")
	}
	keys := sortedKeys(p.Planning.Attributes)
	for _, k := range keys {
		fmt.Fprintf(&b, "Attribute %q, one of: %s\n", k, strings.Join(p.Planning.Attributes[k], ", "))
	}
	if len(keys) > 0 {
		fmt.Fprintf(&b, "Every asset has an \"attributes\" object with a value for each attribute: %s.\n", strings.Join(keys, ", "))
	}
	if p.Planning.IDPattern != "" {
		fmt.Fprintf(&b, "Every id matches %s and is unique.\n", p.Planning.IDPattern)
	}
	fmt.Fprintf(&b, "\nReturn exactly %d assets. Each subject describes only the object itself, in English, "+
		"as a short visual description of shape, materials and colours; never the background, the style or the framing, "+
		"which the style sheet adds. The art direction gives a summary, a palette of 4 to 8 colour names, a mood and "+
		"3 to 6 short rules that every image follows.\n", maxAssets)
	return b.String()
}

// NormalizePlan turns a planner draft into a plan that satisfies the profile:
// known categories and placements, allowed attribute values, unique ids that
// match the pattern and prefix, bounded titles and asset count. Every repair
// is reported in Issues; nothing is silently invented except defaults.
func NormalizePlan(p *Profile, d PlanDraft, brief, packID, theme string, maxAssets int) (Plan, error) {
	if !packIDPattern.MatchString(packID) {
		return Plan{}, fmt.Errorf("invalid pack_id %q", packID)
	}
	if maxAssets <= 0 || maxAssets > p.Planning.MaxAssets {
		maxAssets = p.Planning.MaxAssets
	}
	plan := Plan{Schema: "image-studio.plan/v1", PackID: packID, Title: strings.TrimSpace(d.Title), Theme: theme,
		Brief: brief, Profile: p.Key, ArtDirection: d.ArtDirection, Issues: []string{}}
	if plan.Title == "" {
		plan.Title = packID
	}
	var idRe *regexp.Regexp
	if p.Planning.IDPattern != "" {
		idRe = regexp.MustCompile(p.Planning.IDPattern)
	}
	seen := map[string]bool{}
	for n, a := range d.Assets {
		where := fmt.Sprintf("asset %d", n+1)
		cat, ok := p.Category(strings.TrimSpace(strings.ToLower(a.Category)))
		if !ok {
			plan.Issues = append(plan.Issues, fmt.Sprintf("%s: unknown category %q, dropped", where, a.Category))
			continue
		}
		a.Category = cat.Key
		a.Placement = strings.TrimSpace(strings.ToLower(a.Placement))
		if len(cat.Placements) > 0 && !contains(cat.Placements, a.Placement) {
			if a.Placement != "" {
				plan.Issues = append(plan.Issues, fmt.Sprintf("%s: placement %q replaced by %q", where, a.Placement, cat.Placements[0]))
			}
			a.Placement = cat.Placements[0]
		} else if len(cat.Placements) == 0 {
			a.Placement = ""
		}
		id := slugReplacer.ReplaceAllString(strings.ToLower(strings.TrimSpace(a.ID)), "_")
		id = strings.Trim(id, "_")
		if cat.IDPrefix != "" && !strings.HasPrefix(id, cat.IDPrefix) {
			id = cat.IDPrefix + strings.TrimPrefix(id, strings.TrimSuffix(cat.IDPrefix, "_"))
			id = strings.ReplaceAll(id, "__", "_")
		}
		if len(id) > 32 {
			id = strings.TrimRight(id[:32], "_")
		}
		base := id
		for k := 2; seen[id]; k++ {
			suffix := fmt.Sprintf("_%d", k)
			id = base[:min(len(base), 32-len(suffix))] + suffix
		}
		if idRe != nil && !idRe.MatchString(id) {
			plan.Issues = append(plan.Issues, fmt.Sprintf("%s: id %q does not match %s, dropped", where, id, p.Planning.IDPattern))
			continue
		}
		if id != a.ID {
			plan.Issues = append(plan.Issues, fmt.Sprintf("%s: id %q normalized to %q", where, a.ID, id))
		}
		a.ID = id
		seen[id] = true
		a.Title = strings.TrimSpace(a.Title)
		if a.Title == "" {
			a.Title = id
		}
		if r := []rune(a.Title); len(r) > 80 {
			a.Title = strings.TrimSpace(string(r[:80]))
		}
		a.Subject = strings.TrimSpace(a.Subject)
		if a.Subject == "" {
			a.Subject = a.Title
		}
		attrs := map[string]string{}
		for _, k := range sortedKeys(p.Planning.Attributes) {
			allowed := p.Planning.Attributes[k]
			v := strings.TrimSpace(strings.ToLower(a.Attributes[k]))
			if !contains(allowed, v) {
				plan.Issues = append(plan.Issues, fmt.Sprintf("%s: %s %q replaced by %q", where, k, a.Attributes[k], allowed[0]))
				v = allowed[0]
			}
			attrs[k] = v
		}
		a.Attributes = attrs
		if len(plan.Assets) == maxAssets {
			plan.Issues = append(plan.Issues, fmt.Sprintf("%s: over the limit of %d assets, dropped", where, maxAssets))
			continue
		}
		plan.Assets = append(plan.Assets, a)
	}
	if len(plan.Assets) == 0 {
		return plan, fmt.Errorf("the plan has no usable asset: %s", strings.Join(plan.Issues, "; "))
	}
	return plan, nil
}

// Job is everything one asset production needs; it travels as the for_each
// item, so it is self-contained.
type Job struct {
	Schema      string          `json:"schema"`
	PackID      string          `json:"pack_id"`
	Theme       string          `json:"theme"`
	Index       int             `json:"index"`
	Dir         string          `json:"dir"`
	Asset       Asset           `json:"asset"`
	Prompt      string          `json:"prompt"`
	AspectRatio string          `json:"aspect_ratio"`
	Model       string          `json:"model"`
	Profile     string          `json:"profile"`
	BoxKey      string          `json:"box_key,omitempty"`
	Export      ExportConfig    `json:"export"`
	Judge       JudgeConfig     `json:"judge"`
	JudgePrompt string          `json:"judge_prompt"`
	Document    *DocumentConfig `json:"document,omitempty"`
	Price       *PriceTag       `json:"price,omitempty"`
}

// PriceTag is a suggested price, never a sale.
type PriceTag struct {
	Value int    `json:"value"`
	Unit  string `json:"unit"`
	Note  string `json:"note,omitempty"`
}

// StyleSheet is the shared prompt material of a pack.
type StyleSheet struct {
	Schema   string   `json:"schema"`
	PackID   string   `json:"pack_id"`
	Profile  string   `json:"profile"`
	Prefix   string   `json:"prefix"`
	Suffix   string   `json:"suffix"`
	Palette  []string `json:"palette"`
	Rules    []string `json:"rules"`
	AssetIDs []string `json:"asset_ids"`
}

// BuildStyleSheet derives one prompt prefix and suffix for the whole pack,
// so every image shares the same style words, and one job per asset.
func BuildStyleSheet(p *Profile, plan Plan, root string) (StyleSheet, []Job) {
	g := p.Generation
	ad := plan.ArtDirection
	var pre strings.Builder
	pre.WriteString(strings.TrimSpace(g.StylePrefix))
	if ad.Summary != "" {
		fmt.Fprintf(&pre, " Collection style: %s.", strings.TrimSuffix(strings.TrimSpace(ad.Summary), "."))
	}
	if len(ad.Palette) > 0 {
		fmt.Fprintf(&pre, " Shared palette: %s.", strings.Join(ad.Palette, ", "))
	}
	if ad.Mood != "" {
		fmt.Fprintf(&pre, " Mood: %s.", strings.TrimSuffix(strings.TrimSpace(ad.Mood), "."))
	}
	var suf []string
	for _, r := range ad.Rules {
		if r = strings.TrimSpace(r); r != "" {
			suf = append(suf, strings.TrimSuffix(r, "."))
		}
	}
	suffix := ""
	if len(suf) > 0 {
		suffix = "Rules: " + strings.Join(suf, "; ") + "."
	}
	for _, s := range []string{g.Composition, g.Background, g.Avoid} {
		if s = strings.TrimSpace(s); s != "" {
			suffix = strings.TrimSpace(suffix + " " + s)
		}
	}
	sheet := StyleSheet{Schema: "image-studio.style/v1", PackID: plan.PackID, Profile: p.Key, Prefix: pre.String(),
		Suffix: suffix, Palette: ad.Palette, Rules: suf}
	jobs := make([]Job, 0, len(plan.Assets))
	for i, a := range plan.Assets {
		sheet.AssetIDs = append(sheet.AssetIDs, a.ID)
		jobs = append(jobs, newJob(p, plan, a, i, root, sheet))
	}
	return sheet, jobs
}

func newJob(p *Profile, plan Plan, a Asset, index int, root string, sheet StyleSheet) Job {
	subject := a.Subject
	if a.Placement != "" {
		subject = fmt.Sprintf("%s (worn or placed: %s)", subject, a.Placement)
	}
	framing := ""
	if c, ok := p.Category(a.Category); ok && c.Framing != "" {
		framing = " Framing: " + strings.TrimSuffix(strings.TrimSpace(c.Framing), ".") + "."
	}
	prompt := strings.TrimSpace(fmt.Sprintf("%s Subject: %s.%s %s", sheet.Prefix, strings.TrimSuffix(subject, "."), framing, sheet.Suffix))
	model := p.Generation.Model
	if model == "" {
		model = "image-default"
	}
	job := Job{Schema: "image-studio.job/v1", PackID: plan.PackID, Theme: plan.Theme, Index: index,
		Dir: strings.TrimSuffix(root, "/") + "/" + plan.PackID + "/" + a.ID, Asset: a, Prompt: prompt,
		AspectRatio: p.Generation.AspectRatio, Model: model, Profile: p.Key, Export: p.Export, Judge: p.Judge,
		Document: p.Document}
	if p.Export.Kind == "pixel-grid" {
		job.BoxKey = a.Category
		if a.Placement != "" {
			job.BoxKey = a.Category + ":" + a.Placement
		}
		// Each job only carries its own box.
		job.Export.Boxes = map[string]Box{job.BoxKey: p.Export.Boxes[job.BoxKey]}
	}
	note := ""
	if c, ok := p.Category(a.Category); ok && c.Review != "" {
		note = "\n" + strings.TrimSpace(c.Review)
	}
	job.JudgePrompt = fmt.Sprintf("%s\n\nExpected subject: %s (%s).%s\nAnswer with one JSON object only, no prose: "+
		`{"score": <0-10>, "pass": <true|false>, "issues": [<short English strings>]}.`,
		strings.TrimSpace(p.Judge.Prompt), a.Subject, a.Title, note)
	if pr := p.Pricing; pr != nil {
		if v, ok := pr.Values[a.Attributes[pr.Attribute]]; ok {
			job.Price = &PriceTag{Value: v, Unit: pr.Unit, Note: pr.Note}
		}
	}
	return job
}

// ParseDraft accepts the planner output as an object or a JSON string.
func ParseDraft(raw json.RawMessage) (PlanDraft, error) {
	var d PlanDraft
	var s string
	if json.Unmarshal(raw, &s) == nil {
		raw = json.RawMessage(extractJSONObject(s))
	}
	if err := json.Unmarshal(raw, &d); err != nil {
		return d, fmt.Errorf("planner output: %w", err)
	}
	return d, nil
}

func contains(list []string, v string) bool {
	for _, x := range list {
		if x == v {
			return true
		}
	}
	return false
}

func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// extractJSONObject returns the first balanced {...} of a text, or the text.
func extractJSONObject(s string) string {
	start := strings.Index(s, "{")
	if start < 0 {
		return s
	}
	depth, inStr, esc := 0, false, false
	for i := start; i < len(s); i++ {
		c := s[i]
		switch {
		case esc:
			esc = false
		case c == '\\' && inStr:
			esc = true
		case c == '"':
			inStr = !inStr
		case inStr:
		case c == '{':
			depth++
		case c == '}':
			depth--
			if depth == 0 {
				return s[start : i+1]
			}
		}
	}
	return s[start:]
}
