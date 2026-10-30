package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

// BuildDocument fills the profile document for one asset. Field sources are
// asset.id, asset.title, asset.category, asset.placement,
// asset.attributes.<name>, pack.id, pack.theme and export.art; by_attribute
// merges the object listed under the asset's value of that attribute.
func BuildDocument(d *DocumentConfig, job Job, art any) (map[string]any, error) {
	doc, _ := deepCopy(d.Template).(map[string]any)
	if doc == nil {
		doc = map[string]any{}
	}
	for _, key := range sortedKeys(d.Fields) {
		src := d.Fields[key]
		var v any
		switch {
		case src == "asset.id":
			v = job.Asset.ID
		case src == "asset.title":
			v = job.Asset.Title
		case src == "asset.category":
			v = job.Asset.Category
		case src == "asset.placement":
			v = job.Asset.Placement
		case strings.HasPrefix(src, "asset.attributes."):
			v = job.Asset.Attributes[strings.TrimPrefix(src, "asset.attributes.")]
		case src == "pack.id":
			v = job.PackID
		case src == "pack.theme":
			v = job.Theme
		case src == "export.art":
			v = art
		default:
			return nil, fmt.Errorf("document field %q: unknown source %q", key, src)
		}
		doc[key] = v
	}
	for _, attr := range sortedKeys(d.By) {
		for k, v := range d.By[attr][job.Asset.Attributes[attr]] {
			doc[k] = deepCopy(v)
		}
	}
	return doc, nil
}

func deepCopy(v any) any {
	raw, _ := json.Marshal(v)
	var out any
	_ = json.Unmarshal(raw, &out)
	return out
}

// Review is the parsed vision judgement.
type Review struct {
	Available bool     `json:"available"`
	Score     float64  `json:"score"`
	Pass      bool     `json:"pass"`
	Issues    []string `json:"issues"`
}

// ParseReview finds the JSON judgement in a vision tool result, wherever the
// provider put the text.
func ParseReview(result any) Review {
	var texts []string
	collectStrings(result, &texts)
	for _, t := range texts {
		if !strings.Contains(t, "score") {
			continue
		}
		var r struct {
			Score  *float64 `json:"score"`
			Pass   *bool    `json:"pass"`
			Issues []string `json:"issues"`
		}
		if json.Unmarshal([]byte(extractJSONObject(t)), &r) == nil && r.Score != nil {
			out := Review{Available: true, Score: *r.Score, Issues: r.Issues}
			if r.Pass != nil {
				out.Pass = *r.Pass
			}
			if out.Issues == nil {
				out.Issues = []string{}
			}
			return out
		}
	}
	return Review{Issues: []string{"vision review unavailable or unreadable"}}
}

func collectStrings(v any, out *[]string) {
	switch t := v.(type) {
	case string:
		*out = append(*out, t)
		var inner any
		if strings.HasPrefix(strings.TrimSpace(t), "{") && json.Unmarshal([]byte(t), &inner) == nil {
			collectStrings(inner, out)
		}
	case map[string]any:
		for _, k := range sortedKeys(t) {
			collectStrings(t[k], out)
		}
	case []any:
		for _, x := range t {
			collectStrings(x, out)
		}
	}
}

// Verdict decides what happens to an attempt.
type Verdict struct {
	Next    string   `json:"next"`   // accept | retry
	Status  string   `json:"status"` // accepted | needs_review
	Score   float64  `json:"score"`
	Issues  []string `json:"issues"`
	Checks  []string `json:"failed_checks"`
	Attempt int      `json:"attempt"`
}

// Decide combines the vision review with the deterministic export checks.
// The first attempt retries on any failure; the last attempt is kept and
// flagged for human review.
func Decide(job Job, stats map[string]any, review Review, attempt int, final bool) Verdict {
	v := Verdict{Score: review.Score, Issues: append([]string{}, review.Issues...), Checks: []string{}, Attempt: attempt}
	if job.Export.Kind == "pixel-grid" {
		if n := intOf(stats["opaque_cells"]); job.Judge.MinOpaqueCell > 0 && n < job.Judge.MinOpaqueCell {
			v.Checks = append(v.Checks, fmt.Sprintf("only %d opaque cells (minimum %d)", n, job.Judge.MinOpaqueCell))
		}
		if r := floatOf(stats["box_fill_ratio"]); job.Judge.MinFillRatio > 0 && r < job.Judge.MinFillRatio {
			v.Checks = append(v.Checks, fmt.Sprintf("fills %.0f%% of its box (minimum %.0f%%)", r*100, job.Judge.MinFillRatio*100))
		}
	}
	good := review.Available && review.Pass && review.Score >= job.Judge.MinScore && len(v.Checks) == 0
	switch {
	case good:
		v.Next, v.Status = "accept", "accepted"
	case !final:
		v.Next, v.Status = "retry", "needs_review"
	default:
		v.Next, v.Status = "accept", "needs_review"
	}
	return v
}

// RetryPrompt adds the reasons of the first refusal to the prompt.
func RetryPrompt(job Job, v Verdict) string {
	reasons := append(append([]string{}, v.Issues...), v.Checks...)
	if len(reasons) == 0 {
		return job.Prompt
	}
	if len(reasons) > 5 {
		reasons = reasons[:5]
	}
	return job.Prompt + " Previous attempt was rejected; fix: " + strings.Join(reasons, "; ") + "."
}

func intOf(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case json.Number:
		n, _ := t.Int64()
		return int(n)
	}
	return 0
}

func floatOf(v any) float64 {
	switch t := v.(type) {
	case float64:
		return t
	case int:
		return float64(t)
	case json.Number:
		f, _ := t.Float64()
		return f
	}
	return 0
}
