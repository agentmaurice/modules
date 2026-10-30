package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
)

// ProfileSchema identifies the output profile format read by every op.
const ProfileSchema = "image-studio.profile/v1"

// Profile describes one output target as data: how to plan assets, how to
// prompt the image model, how to export and judge the result, and which
// document accompanies each exported asset. The module has no target-specific
// code; a new target is a new profile.
type Profile struct {
	Schema     string          `json:"schema"`
	Key        string          `json:"key"`
	Title      string          `json:"title"`
	Planning   Planning        `json:"planning"`
	Generation Generation      `json:"generation"`
	Export     ExportConfig    `json:"export"`
	Judge      JudgeConfig     `json:"judge"`
	Document   *DocumentConfig `json:"document,omitempty"`
	Pricing    *Pricing        `json:"pricing,omitempty"`
}

// Planning constrains the asset list produced from a brief.
type Planning struct {
	Guidance   string              `json:"guidance"`
	MaxAssets  int                 `json:"max_assets"`
	IDPattern  string              `json:"id_pattern"`
	Categories []Category          `json:"categories"`
	Attributes map[string][]string `json:"attributes,omitempty"`
}

// Category is a kind of asset (a slot, a banner format...).
type Category struct {
	Key         string   `json:"key"`
	IDPrefix    string   `json:"id_prefix,omitempty"`
	Description string   `json:"description,omitempty"`
	Placements  []string `json:"placements,omitempty"`
	// Framing is added to the prompt of every asset of the category, so the
	// generated object already has the proportions of its export box.
	Framing string `json:"framing,omitempty"`
	// Review tells the vision reviewer how the export shows the category.
	Review string `json:"review,omitempty"`
}

// Generation holds the prompt fragments shared by every asset of a profile.
type Generation struct {
	AspectRatio string `json:"aspect_ratio"`
	Model       string `json:"model,omitempty"`
	StylePrefix string `json:"style_prefix"`
	Composition string `json:"composition,omitempty"`
	Background  string `json:"background,omitempty"`
	Avoid       string `json:"avoid,omitempty"`
}

// ExportConfig selects and parameterizes an export kind.
type ExportConfig struct {
	Kind string `json:"kind"` // pixel-grid | raster

	// pixel-grid
	Size         int            `json:"size,omitempty"`
	MaxColors    int            `json:"max_colors,omitempty"`
	Outline      string         `json:"outline,omitempty"`
	Letters      string         `json:"letters,omitempty"`
	PreviewScale int            `json:"preview_scale,omitempty"`
	Background   BackgroundCfg  `json:"background,omitempty"`
	Boxes        map[string]Box `json:"boxes,omitempty"`

	// raster
	Width  int    `json:"width,omitempty"`
	Height int    `json:"height,omitempty"`
	Fit    string `json:"fit,omitempty"` // cover | contain
	File   string `json:"file,omitempty"`
}

// BackgroundCfg controls background removal before the pixel-grid reduction.
type BackgroundCfg struct {
	Tolerance float64 `json:"tolerance,omitempty"`
	// Defringe removes anti-aliased blends between the subject and the
	// background (pink seams on a magenta background) and restores the
	// subject colour of the edge pixels that stay.
	Defringe bool `json:"defringe,omitempty"`
	// ClearEnclosed also clears background-coloured pixels that the border
	// flood cannot reach (holes between antlers, inside a ring). Leave it
	// off when the subject may contain the background colour.
	ClearEnclosed bool `json:"clear_enclosed,omitempty"`
}

// JudgeConfig drives the vision review and the deterministic checks.
type JudgeConfig struct {
	Prompt        string  `json:"prompt"`
	MinScore      float64 `json:"min_score"`
	MinOpaqueCell int     `json:"min_opaque_cells,omitempty"`
	MinFillRatio  float64 `json:"min_box_fill_ratio,omitempty"`
}

// DocumentConfig builds the sidecar document written next to each asset.
type DocumentConfig struct {
	File     string                               `json:"file"`
	Template map[string]any                       `json:"template"`
	Fields   map[string]string                    `json:"fields"`
	By       map[string]map[string]map[string]any `json:"by_attribute,omitempty"`
}

// Pricing attaches a suggested price to assets from one attribute.
type Pricing struct {
	Attribute string         `json:"attribute"`
	Unit      string         `json:"unit"`
	Values    map[string]int `json:"values"`
	Note      string         `json:"note,omitempty"`
}

var profileKeyPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,63}$`)

// ParseProfile decodes and validates a profile document.
func ParseProfile(raw []byte) (*Profile, error) {
	var p Profile
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&p); err != nil {
		return nil, fmt.Errorf("profile: %w", err)
	}
	if err := p.Validate(); err != nil {
		return nil, err
	}
	return &p, nil
}

// Validate checks the profile invariants used by the ops.
func (p *Profile) Validate() error {
	var errs []string
	if p.Schema != ProfileSchema {
		errs = append(errs, "schema must be "+ProfileSchema)
	}
	if !profileKeyPattern.MatchString(p.Key) {
		errs = append(errs, "key must match "+profileKeyPattern.String())
	}
	if len(p.Planning.Categories) == 0 {
		errs = append(errs, "planning.categories is empty")
	}
	if p.Planning.MaxAssets < 1 || p.Planning.MaxAssets > 100 {
		errs = append(errs, "planning.max_assets must be in 1..100")
	}
	if p.Planning.IDPattern != "" {
		if _, err := regexp.Compile(p.Planning.IDPattern); err != nil {
			errs = append(errs, "planning.id_pattern: "+err.Error())
		}
	}
	switch p.Export.Kind {
	case "pixel-grid":
		e := p.Export
		if e.Size < 8 || e.Size > 128 {
			errs = append(errs, "export.size must be in 8..128")
		}
		if e.MaxColors < 2 || e.MaxColors > 52 {
			errs = append(errs, "export.max_colors must be in 2..52")
		}
		if !hexPattern.MatchString(e.Outline) {
			errs = append(errs, "export.outline must be a #rrggbb colour")
		}
		if len(strings.ReplaceAll(e.Letters, "K", "")) < e.MaxColors-1 {
			errs = append(errs, "export.letters must hold at least max_colors-1 letters besides the outline letter K")
		}
		for _, c := range p.Planning.Categories {
			if _, ok := e.Boxes[c.Key]; !ok {
				errs = append(errs, "export.boxes has no box for category "+c.Key)
			}
			for _, pl := range c.Placements {
				if _, ok := e.Boxes[c.Key+":"+pl]; !ok {
					errs = append(errs, "export.boxes has no box for "+c.Key+":"+pl)
				}
			}
		}
		for k, b := range e.Boxes {
			if b.W < 1 || b.H < 1 || b.X < 0 || b.Y < 0 || b.X+b.W > e.Size || b.Y+b.H > e.Size {
				errs = append(errs, "export.boxes."+k+" is outside the grid")
			}
			if b.KeepTop < 0 || b.KeepTop > 1 {
				errs = append(errs, "export.boxes."+k+".keep_top must be in 0..1")
			}
		}
	case "raster":
		e := p.Export
		if e.Width < 16 || e.Height < 16 || e.Width > 4096 || e.Height > 4096 {
			errs = append(errs, "export.width and export.height must be in 16..4096")
		}
		if e.Fit != "cover" && e.Fit != "contain" {
			errs = append(errs, "export.fit must be cover or contain")
		}
	default:
		errs = append(errs, "export.kind must be pixel-grid or raster")
	}
	if p.Document != nil && !plainFileName(p.Document.File) {
		errs = append(errs, "document.file must be a plain file name")
	}
	if p.Export.File != "" && !plainFileName(p.Export.File) {
		errs = append(errs, "export.file must be a plain file name")
	}
	for k, v := range p.Planning.Attributes {
		if len(v) == 0 {
			errs = append(errs, "planning.attributes."+k+" is empty")
		}
	}
	if len(errs) > 0 {
		return errors.New("profile: " + strings.Join(errs, "; "))
	}
	return nil
}

// Category returns the category of the given key.
func (p *Profile) Category(key string) (Category, bool) {
	for _, c := range p.Planning.Categories {
		if c.Key == key {
			return c, true
		}
	}
	return Category{}, false
}

var hexPattern = regexp.MustCompile(`^#[0-9a-f]{6}$`)

var fileNamePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)

func plainFileName(name string) bool {
	return fileNamePattern.MatchString(name) && !strings.Contains(name, "..")
}
