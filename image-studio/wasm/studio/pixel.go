package main

import (
	"bytes"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
	"sort"
	"strings"
)

// Box is the target area of a category inside the square grid.
type Box struct {
	X int `json:"x"`
	Y int `json:"y"`
	W int `json:"w"`
	H int `json:"h"`
	// KeepTop keeps only this fraction of the subject's height, from its
	// top (0 or 1 keeps all): a garment drawn whole still fills a wide,
	// short box with its readable part.
	KeepTop float64 `json:"keep_top,omitempty"`
}

// Art is the text-grid drawing: one letter per pixel, "." is transparent.
type Art struct {
	Size    int               `json:"size"`
	Palette map[string]string `json:"palette"`
	Frames  []Frame           `json:"frames"`
}

// Frame holds the rows of one frame, starting at row Py.
type Frame struct {
	Py int      `json:"py"`
	Px []string `json:"px"`
}

// GridStats describes a pixel-grid conversion.
type GridStats struct {
	Colors       int     `json:"colors"`
	OpaqueCells  int     `json:"opaque_cells"`
	OutlineCells int     `json:"outline_cells"`
	BoxFillRatio float64 `json:"box_fill_ratio"`
	Background   string  `json:"background"`
	DefringedPx  int     `json:"defringed_pixels"`
	ClearedPx    int     `json:"cleared_pixels"`
	SourceW      int     `json:"source_w"`
	SourceH      int     `json:"source_h"`
}

// GridOptions control the pixel-grid conversion.
type GridOptions struct {
	Box          Box
	Size         int
	MaxColors    int
	Tolerance    float64
	Defringe     bool
	ClearHoles   bool
	Outline      string
	Letters      string
	PreviewScale int
}

// GridOptionsFor derives the conversion options of one category placement.
func GridOptionsFor(e ExportConfig, boxKey string) (GridOptions, error) {
	box, ok := e.Boxes[boxKey]
	if !ok {
		return GridOptions{}, fmt.Errorf("no export box for %q", boxKey)
	}
	tol := e.Background.Tolerance
	if tol <= 0 {
		tol = 70
	}
	scale := e.PreviewScale
	if scale <= 0 {
		scale = 8
	}
	return GridOptions{Box: box, Size: e.Size, MaxColors: e.MaxColors, Tolerance: tol, Defringe: e.Background.Defringe, ClearHoles: e.Background.ClearEnclosed,
		Outline: e.Outline, Letters: e.Letters, PreviewScale: scale}, nil
}

type rgb struct{ r, g, b float64 }

const darkLuminance = 70

func luminance(c rgb) float64 { return 0.2126*c.r + 0.7152*c.g + 0.0722*c.b }

func dist2(a, b rgb) float64 {
	return (a.r-b.r)*(a.r-b.r) + (a.g-b.g)*(a.g-b.g) + (a.b-b.b)*(a.b-b.b)
}

func bucketKey(c rgb) int {
	return (int(c.r)>>4)<<8 | (int(c.g)>>4)<<4 | int(c.b)>>4
}

// raster is a decoded image as straight 8-bit RGB plus alpha, packed to keep
// a 1024x1024 source within a few megabytes inside the WASM worker.
type raster struct {
	w, h int
	rgb  []uint8
	a    []uint8
}

func (r *raster) at(i int) rgb {
	return rgb{float64(r.rgb[3*i]), float64(r.rgb[3*i+1]), float64(r.rgb[3*i+2])}
}

func (r *raster) set(i int, c rgb) {
	r.rgb[3*i], r.rgb[3*i+1], r.rgb[3*i+2] = clamp8(c.r), clamp8(c.g), clamp8(c.b)
}

func decodeRaster(data []byte) (*raster, error) {
	img, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("decode image: %w", err)
	}
	return rasterFromImage(img), nil
}

func rasterFromImage(img image.Image) *raster {
	b := img.Bounds()
	r := &raster{w: b.Dx(), h: b.Dy()}
	r.rgb = make([]uint8, 3*r.w*r.h)
	r.a = make([]uint8, r.w*r.h)
	put := func(i int, c color.NRGBA) {
		r.rgb[3*i], r.rgb[3*i+1], r.rgb[3*i+2], r.a[i] = c.R, c.G, c.B, c.A
	}
	switch src := img.(type) {
	case *image.NRGBA:
		for y := 0; y < r.h; y++ {
			for x := 0; x < r.w; x++ {
				put(y*r.w+x, src.NRGBAAt(b.Min.X+x, b.Min.Y+y))
			}
		}
	case *image.RGBA:
		for y := 0; y < r.h; y++ {
			for x := 0; x < r.w; x++ {
				c := src.RGBAAt(b.Min.X+x, b.Min.Y+y)
				if c.A != 0 && c.A != 255 {
					c.R = uint8(uint32(c.R) * 255 / uint32(c.A))
					c.G = uint8(uint32(c.G) * 255 / uint32(c.A))
					c.B = uint8(uint32(c.B) * 255 / uint32(c.A))
				}
				put(y*r.w+x, color.NRGBA{c.R, c.G, c.B, c.A})
			}
		}
	default:
		for y := 0; y < r.h; y++ {
			for x := 0; x < r.w; x++ {
				put(y*r.w+x, color.NRGBAModel.Convert(img.At(b.Min.X+x, b.Min.Y+y)).(color.NRGBA))
			}
		}
	}
	return r
}

func (r *raster) neighbours(i int) [4]int {
	x, y := i%r.w, i/r.w
	return [4]int{ifThen(x > 0, i-1), ifThen(x < r.w-1, i+1), ifThen(y > 0, i-r.w), ifThen(y < r.h-1, i+r.w)}
}

func ifThen(ok bool, v int) int {
	if ok {
		return v
	}
	return -1
}

// borderBackground returns the dominant colour of the opaque border pixels.
func borderBackground(r *raster) (rgb, bool) {
	var border []int
	for x := 0; x < r.w; x++ {
		border = append(border, x, (r.h-1)*r.w+x)
	}
	for y := 0; y < r.h; y++ {
		border = append(border, y*r.w, y*r.w+r.w-1)
	}
	counts := map[int]int{}
	for _, i := range border {
		if r.a[i] >= 128 {
			counts[bucketKey(r.at(i))]++
		}
	}
	bestKey, best := -1, 0
	for k, n := range counts {
		if n > best || (n == best && k < bestKey) {
			bestKey, best = k, n
		}
	}
	var bg rgb
	n := 0.0
	for _, i := range border {
		if r.a[i] >= 128 && bucketKey(r.at(i)) == bestKey {
			bg.r += float64(r.rgb[3*(i)+0])
			bg.g += float64(r.rgb[3*(i)+1])
			bg.b += float64(r.rgb[3*(i)+2])
			n++
		}
	}
	if n == 0 {
		return rgb{}, false
	}
	return rgb{bg.r / n, bg.g / n, bg.b / n}, true
}

// foregroundMask flood-fills from the border through pixels close to the
// border colour (or transparent ones); everything else is foreground.
func foregroundMask(r *raster, tolerance float64) ([]bool, rgb, bool) {
	bg, hasBg := borderBackground(r)
	tol2 := tolerance * tolerance
	isBg := func(i int) bool { return r.a[i] < 128 || (hasBg && dist2(r.at(i), bg) <= tol2) }
	mask := make([]bool, r.w*r.h)
	for i := range mask {
		mask[i] = true
	}
	var stack []int
	push := func(i int) {
		if i >= 0 && mask[i] && isBg(i) {
			mask[i] = false
			stack = append(stack, i)
		}
	}
	for x := 0; x < r.w; x++ {
		push(x)
		push((r.h-1)*r.w + x)
	}
	for y := 0; y < r.h; y++ {
		push(y * r.w)
		push(y*r.w + r.w - 1)
	}
	for len(stack) > 0 {
		i := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		for _, j := range r.neighbours(i) {
			push(j)
		}
	}
	return mask, bg, hasBg
}

// defringe removes what the generator paints between the subject and a flat
// background: anti-aliased seams and soft glows. Each such pixel is a blend
// p = a*f + (1-a)*bg of the background and one of the solid subject colours
// f. Starting from the background, the fill grows into every pixel that is
// mostly background along such a segment (a < 0.5, small residual), up to a
// width proportional to the image. Edge pixels that stay take the colour f,
// so no blend survives as a palette entry of its own after the reduction.
// It returns the number of cleared and recoloured pixels.
func defringe(r *raster, mask []bool, bg rgb) (cleared, recoloured int) {
	solids := solidColours(r, mask, bg)
	if len(solids) == 0 {
		return 0, 0
	}
	maxWidth := max(4, min(r.w, r.h)*8/100)
	band := max(2, min(r.w, r.h)/256)
	const maxResidual2 = 40 * 40
	blend := func(p rgb) (float64, rgb, bool) {
		bestRes, bestA, best := math.Inf(1), 1.0, rgb{}
		for _, f := range solids {
			d := rgb{f.r - bg.r, f.g - bg.g, f.b - bg.b}
			dd := d.r*d.r + d.g*d.g + d.b*d.b
			a := ((p.r-bg.r)*d.r + (p.g-bg.g)*d.g + (p.b-bg.b)*d.b) / dd
			a = math.Max(0, math.Min(1, a))
			if res := dist2(p, rgb{bg.r + a*d.r, bg.g + a*d.g, bg.b + a*d.b}); res < bestRes {
				bestRes, bestA, best = res, a, f
			}
		}
		return bestA, best, bestRes <= maxResidual2
	}
	depth := make([]int, len(mask))
	var queue []int
	for i, fg := range mask {
		if !fg {
			queue = append(queue, i)
		}
	}
	for head := 0; head < len(queue); head++ {
		i := queue[head]
		if depth[i] >= maxWidth {
			continue
		}
		for _, j := range r.neighbours(i) {
			if j < 0 || !mask[j] {
				continue
			}
			if a, _, ok := blend(r.at(j)); ok && a < 0.5 {
				mask[j] = false
				depth[j] = depth[i] + 1
				cleared++
				queue = append(queue, j)
			}
		}
	}
	// Recolour the remaining seam: foreground pixels within band of the
	// background that are still a blend.
	dist := make([]int, len(mask))
	queue = queue[:0]
	for i, fg := range mask {
		if fg {
			dist[i] = -1
		} else {
			queue = append(queue, i)
		}
	}
	for head := 0; head < len(queue); head++ {
		i := queue[head]
		if dist[i] >= band {
			continue
		}
		for _, j := range r.neighbours(i) {
			if j >= 0 && dist[j] < 0 {
				dist[j] = dist[i] + 1
				queue = append(queue, j)
			}
		}
	}
	for i, fg := range mask {
		if !fg || dist[i] < 1 {
			continue
		}
		if a, f, ok := blend(r.at(i)); ok && a < 0.92 {
			r.set(i, f)
			recoloured++
		}
	}
	return cleared, recoloured
}

// solidColours clusters the subject interior (pixels at least three steps
// from the background) into at most twelve colours, leaving out those too
// close to the background to define a blend direction.
func solidColours(r *raster, mask []bool, bg rgb) []rgb {
	interior := make([]bool, len(mask))
	copy(interior, mask)
	for step := 0; step < 3; step++ {
		next := make([]bool, len(interior))
		for i, in := range interior {
			if !in {
				continue
			}
			next[i] = true
			for _, j := range r.neighbours(i) {
				if j < 0 || !interior[j] {
					next[i] = false
					break
				}
			}
		}
		interior = next
	}
	var cells []*rgb
	for i, in := range interior {
		if in && i%3 == 0 {
			c := r.at(i)
			cells = append(cells, &c)
		}
	}
	centers, assign := quantize(cells, 12)
	counts := make([]int, len(centers))
	for _, a := range assign {
		if a >= 0 {
			counts[a]++
		}
	}
	var kept []rgb
	for j, c := range centers {
		if counts[j]*200 >= len(cells) && dist2(c, bg) >= 40*40 {
			kept = append(kept, c)
		}
	}
	// A wide glow is large enough to form a cluster of its own: drop every
	// cluster that is itself a blend of the background and another cluster.
	var out []rgb
	for i, c := range kept {
		blended := false
		for j, f := range kept {
			if i == j {
				continue
			}
			d := rgb{f.r - bg.r, f.g - bg.g, f.b - bg.b}
			a := ((c.r-bg.r)*d.r + (c.g-bg.g)*d.g + (c.b-bg.b)*d.b) / (d.r*d.r + d.g*d.g + d.b*d.b)
			if a > 0.05 && a < 0.6 && dist2(c, rgb{bg.r + a*d.r, bg.g + a*d.g, bg.b + a*d.b}) <= 40*40 {
				blended = true
				break
			}
		}
		if !blended {
			out = append(out, c)
		}
	}
	return out
}

// downsample shrinks the foreground into the box, bottom-aligned and centred.
// Dark buckets are down-weighted so the generator's thick outline does not
// swallow thin fills (bells, antler tines) at grid scale.
func downsample(r *raster, mask []bool, box Box, size int) ([]*rgb, error) {
	x0, y0, x1, y1 := r.w, r.h, -1, -1
	for y := 0; y < r.h; y++ {
		for x := 0; x < r.w; x++ {
			if mask[y*r.w+x] {
				x0, x1 = min(x0, x), max(x1, x)
				y0, y1 = min(y0, y), max(y1, y)
			}
		}
	}
	if x1 < 0 {
		return nil, errors.New("no foreground detected (uniform image?)")
	}
	if box.KeepTop > 0 && box.KeepTop < 1 {
		y1 = y0 + max(0, int(math.Round(float64(y1-y0+1)*box.KeepTop))-1)
		x0, x1 = r.w, -1
		for y := y0; y <= y1; y++ {
			for x := 0; x < r.w; x++ {
				if mask[y*r.w+x] {
					x0, x1 = min(x0, x), max(x1, x)
				}
			}
		}
	}
	cw, ch := x1-x0+1, y1-y0+1
	s := math.Min(float64(box.W)/float64(cw), float64(box.H)/float64(ch))
	tw := max(1, int(math.Round(float64(cw)*s)))
	th := max(1, int(math.Round(float64(ch)*s)))
	ox := box.X + (box.W-tw)/2
	oy := box.Y + box.H - th
	cells := make([]*rgb, size*size)
	type acc struct{ r, g, b, n float64 }
	weight := func(a acc) float64 {
		if luminance(rgb{a.r / a.n, a.g / a.n, a.b / a.n}) < darkLuminance {
			return a.n * 0.4
		}
		return a.n
	}
	for ty := 0; ty < th; ty++ {
		for tx := 0; tx < tw; tx++ {
			sx0, sx1 := x0+tx*cw/tw, x0+(tx+1)*cw/tw
			sy0, sy1 := y0+ty*ch/th, y0+(ty+1)*ch/th
			sx1, sy1 = max(sx1, sx0+1), max(sy1, sy0+1)
			total, opaque := 0, 0
			buckets := map[int]*acc{}
			for y := sy0; y < sy1; y++ {
				for x := sx0; x < sx1; x++ {
					total++
					i := y*r.w + x
					if !mask[i] {
						continue
					}
					opaque++
					k := bucketKey(r.at(i))
					a := buckets[k]
					if a == nil {
						a = &acc{}
						buckets[k] = a
					}
					a.r += float64(r.rgb[3*(i)+0])
					a.g += float64(r.rgb[3*(i)+1])
					a.b += float64(r.rgb[3*(i)+2])
					a.n++
				}
			}
			if opaque*2 < total {
				continue
			}
			keys := make([]int, 0, len(buckets))
			for k := range buckets {
				keys = append(keys, k)
			}
			sort.Ints(keys)
			var best *acc
			for _, k := range keys {
				if best == nil || weight(*buckets[k]) > weight(*best) {
					best = buckets[k]
				}
			}
			cells[(oy+ty)*size+ox+tx] = &rgb{best.r / best.n, best.g / best.n, best.b / best.n}
		}
	}
	return cells, nil
}

// quantize runs a deterministic k-means (farthest-point initialisation).
func quantize(cells []*rgb, k int) ([]rgb, []int) {
	assign := make([]int, len(cells))
	var pts []rgb
	var idx []int
	for i, c := range cells {
		assign[i] = -1
		if c != nil {
			pts = append(pts, *c)
			idx = append(idx, i)
		}
	}
	if len(pts) == 0 {
		return nil, assign
	}
	centers := []rgb{pts[0]}
	for len(centers) < min(k, len(pts)) {
		far, farD := 0, -1.0
		for i, p := range pts {
			d := math.Inf(1)
			for _, c := range centers {
				d = math.Min(d, dist2(p, c))
			}
			if d > farD {
				far, farD = i, d
			}
		}
		if farD < 64 {
			break
		}
		centers = append(centers, pts[far])
	}
	lab := make([]int, len(pts))
	for it := 0; it < 20; it++ {
		for i, p := range pts {
			best, bd := 0, math.Inf(1)
			for j, c := range centers {
				if d := dist2(p, c); d < bd {
					best, bd = j, d
				}
			}
			lab[i] = best
		}
		sums := make([]struct{ r, g, b, n float64 }, len(centers))
		for i, p := range pts {
			s := &sums[lab[i]]
			s.r, s.g, s.b, s.n = s.r+p.r, s.g+p.g, s.b+p.b, s.n+1
		}
		for j, s := range sums {
			if s.n > 0 {
				centers[j] = rgb{s.r / s.n, s.g / s.n, s.b / s.n}
			}
		}
	}
	for i, ci := range idx {
		assign[ci] = lab[i]
	}
	return centers, assign
}

func hexColor(c rgb) string {
	clamp := func(v float64) int { return int(math.Round(math.Max(0, math.Min(255, v)))) }
	return fmt.Sprintf("#%02x%02x%02x", clamp(c.r), clamp(c.g), clamp(c.b))
}

// outlineLetter marks the outline; it is never one of the fill letters.
const outlineLetter = 'K'

func toArt(cells []*rgb, opt GridOptions) (Art, GridStats) {
	size := opt.Size
	letters := strings.ReplaceAll(opt.Letters, string(outlineLetter), "")
	centers, assign := quantize(cells, min(opt.MaxColors-1, len(letters)))
	letterOf := make([]byte, len(centers))
	palette := map[string]string{}
	darkest := -1
	for j, c := range centers {
		letterOf[j] = letters[j]
		palette[string(letters[j])] = hexColor(c)
		if luminance(c) < darkLuminance && (darkest < 0 || luminance(c) < luminance(centers[darkest])) {
			darkest = j
		}
	}
	// The generator already draws a dark outline: map its darkest tone to the
	// outline colour instead of eroding the shape.
	if darkest >= 0 {
		delete(palette, string(letterOf[darkest]))
		letterOf[darkest] = outlineLetter
	}
	grid := bytes.Repeat([]byte{'.'}, size*size)
	for i, a := range assign {
		if a >= 0 {
			grid[i] = letterOf[a]
		}
	}
	// One-cell outer outline where a fill colour touches empty space.
	filled := append([]byte(nil), grid...)
	for y := 0; y < size; y++ {
		for x := 0; x < size; x++ {
			c := filled[y*size+x]
			if c == '.' || c == outlineLetter {
				continue
			}
			for _, d := range [4][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}} {
				nx, ny := x+d[0], y+d[1]
				if nx >= 0 && ny >= 0 && nx < size && ny < size && filled[ny*size+nx] == '.' {
					grid[ny*size+nx] = outlineLetter
				}
			}
		}
	}
	palette[string(outlineLetter)] = opt.Outline
	used := map[byte]bool{}
	st := GridStats{}
	inBox := 0
	for i, c := range grid {
		used[c] = true
		if c != '.' {
			st.OpaqueCells++
			x, y := i%size, i/size
			if x >= opt.Box.X && x < opt.Box.X+opt.Box.W && y >= opt.Box.Y && y < opt.Box.Y+opt.Box.H {
				inBox++
			}
		}
		if c == outlineLetter {
			st.OutlineCells++
		}
	}
	st.BoxFillRatio = math.Round(float64(inBox)/float64(opt.Box.W*opt.Box.H)*1000) / 1000
	for l := range palette {
		if !used[l[0]] {
			delete(palette, l)
		}
	}
	rows := make([]string, size)
	first, last := -1, -1
	for y := 0; y < size; y++ {
		rows[y] = string(grid[y*size : (y+1)*size])
		if strings.Trim(rows[y], ".") != "" {
			if first < 0 {
				first = y
			}
			last = y
		}
	}
	if first < 0 {
		first, last = 0, 0
	}
	st.Colors = len(palette)
	return Art{Size: size, Palette: palette, Frames: []Frame{{Py: first, Px: rows[first : last+1]}}}, st
}

func parseHex(s string) color.NRGBA {
	var r, g, b uint8
	_, _ = fmt.Sscanf(s, "#%02x%02x%02x", &r, &g, &b)
	return color.NRGBA{r, g, b, 255}
}

// renderArt draws the art at the given scale on a checkerboard for review.
func renderArt(art Art, scale int) *image.NRGBA {
	n := art.Size * scale
	img := image.NewNRGBA(image.Rect(0, 0, n, n))
	for y := 0; y < n; y++ {
		for x := 0; x < n; x++ {
			v := uint8(214)
			if ((x/scale)+(y/scale))%2 == 0 {
				v = 236
			}
			img.SetNRGBA(x, y, color.NRGBA{v, v, v, 255})
		}
	}
	f := art.Frames[0]
	for ry, row := range f.Px {
		for cx := 0; cx < len(row); cx++ {
			if row[cx] == '.' {
				continue
			}
			c := parseHex(art.Palette[string(row[cx])])
			for yy := 0; yy < scale; yy++ {
				for xx := 0; xx < scale; xx++ {
					img.SetNRGBA(cx*scale+xx, (f.Py+ry)*scale+yy, c)
				}
			}
		}
	}
	return img
}

// renderArtCloseUp draws only the drawn cells (plus one cell of margin),
// enlarged to about edge pixels, so a reviewer sees the object, not the grid.
func renderArtCloseUp(art Art, edge int) *image.NRGBA {
	f := art.Frames[0]
	x0, x1 := art.Size, -1
	for _, row := range f.Px {
		for x := 0; x < len(row); x++ {
			if row[x] != '.' {
				x0, x1 = min(x0, x), max(x1, x)
			}
		}
	}
	if x1 < 0 {
		return renderArt(art, max(1, min(edge, 4096)/art.Size))
	}
	x0, x1 = max(0, x0-1), min(art.Size-1, x1+1)
	y0, y1 := max(0, f.Py-1), min(art.Size-1, f.Py+len(f.Px))
	w, h := x1-x0+1, y1-y0+1
	scale := max(1, min(edge/max(w, h), 4096/art.Size))
	full := renderArt(art, scale)
	return full.SubImage(image.Rect(x0*scale, y0*scale, (x1+1)*scale, (y1+1)*scale)).(*image.NRGBA)
}

func encodePNG(img image.Image) ([]byte, error) {
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// PixelGrid converts a generated image into a text-grid drawing and a preview.
func PixelGrid(data []byte, opt GridOptions) (Art, []byte, GridStats, error) {
	r, err := decodeRaster(data)
	if err != nil {
		return Art{}, nil, GridStats{}, err
	}
	mask, bg, hasBg := foregroundMask(r, opt.Tolerance)
	if opt.ClearHoles && hasBg {
		tol2 := opt.Tolerance * opt.Tolerance
		for i, fg := range mask {
			if fg && dist2(r.at(i), bg) <= tol2 {
				mask[i] = false
			}
		}
	}
	cleared, recoloured := 0, 0
	if opt.Defringe && hasBg {
		cleared, recoloured = defringe(r, mask, bg)
	}
	cells, err := downsample(r, mask, opt.Box, opt.Size)
	if err != nil {
		return Art{}, nil, GridStats{}, err
	}
	art, st := toArt(cells, opt)
	preview, err := encodePNG(renderArt(art, opt.PreviewScale))
	if err != nil {
		return Art{}, nil, GridStats{}, err
	}
	st.SourceW, st.SourceH, st.Background = r.w, r.h, hexColor(bg)
	st.ClearedPx, st.DefringedPx = cleared, recoloured
	return art, preview, st, nil
}
