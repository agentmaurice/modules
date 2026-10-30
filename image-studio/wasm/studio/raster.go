package main

import (
	"fmt"
	"image"
	"image/color"
	_ "image/jpeg"
	"math"
)

// resample scales src to w x h with area averaging (box filter), which is
// exact for reductions and degrades to nearest-neighbour blocks on upscales.
func resample(src *raster, sx, sy, sw, sh, w, h int) *image.NRGBA {
	dst := image.NewNRGBA(image.Rect(0, 0, w, h))
	fx, fy := float64(sw)/float64(w), float64(sh)/float64(h)
	for y := 0; y < h; y++ {
		y0 := float64(sy) + float64(y)*fy
		y1 := y0 + fy
		for x := 0; x < w; x++ {
			x0 := float64(sx) + float64(x)*fx
			x1 := x0 + fx
			var r, g, b, a, wsum float64
			for py := int(y0); py < int(math.Ceil(y1)) && py < src.h; py++ {
				wy := math.Min(y1, float64(py+1)) - math.Max(y0, float64(py))
				for px := int(x0); px < int(math.Ceil(x1)) && px < src.w; px++ {
					wx := math.Min(x1, float64(px+1)) - math.Max(x0, float64(px))
					wt := wx * wy
					if wt <= 0 {
						continue
					}
					i := py*src.w + px
					al := float64(src.a[i]) / 255
					r += float64(src.rgb[3*i+0]) * al * wt
					g += float64(src.rgb[3*i+1]) * al * wt
					b += float64(src.rgb[3*i+2]) * al * wt
					a += al * wt
					wsum += wt
				}
			}
			if wsum == 0 || a == 0 {
				continue
			}
			dst.SetNRGBA(x, y, color.NRGBA{clamp8(r / a), clamp8(g / a), clamp8(b / a), clamp8(a / wsum * 255)})
		}
	}
	return dst
}

func clamp8(v float64) uint8 { return uint8(math.Round(math.Max(0, math.Min(255, v)))) }

// RasterStats describes a raster export.
type RasterStats struct {
	SourceW int    `json:"source_w"`
	SourceH int    `json:"source_h"`
	Width   int    `json:"width"`
	Height  int    `json:"height"`
	Fit     string `json:"fit"`
	Crop    [4]int `json:"crop"`
}

// RasterExport fits the source into width x height. "cover" crops the
// centre to the target ratio; "contain" letterboxes on transparency.
func RasterExport(data []byte, width, height int, fit string) ([]byte, RasterStats, error) {
	src, err := decodeRaster(data)
	if err != nil {
		return nil, RasterStats{}, err
	}
	st := RasterStats{SourceW: src.w, SourceH: src.h, Width: width, Height: height, Fit: fit}
	target := float64(width) / float64(height)
	var out *image.NRGBA
	switch fit {
	case "cover":
		sw, sh := src.w, src.h
		if float64(src.w)/float64(src.h) > target {
			sw = int(math.Round(float64(src.h) * target))
		} else {
			sh = int(math.Round(float64(src.w) / target))
		}
		sx, sy := (src.w-sw)/2, (src.h-sh)/2
		st.Crop = [4]int{sx, sy, sw, sh}
		out = resample(src, sx, sy, sw, sh, width, height)
	case "contain":
		s := math.Min(float64(width)/float64(src.w), float64(height)/float64(src.h))
		tw, th := max(1, int(math.Round(float64(src.w)*s))), max(1, int(math.Round(float64(src.h)*s)))
		inner := resample(src, 0, 0, src.w, src.h, tw, th)
		out = image.NewNRGBA(image.Rect(0, 0, width, height))
		ox, oy := (width-tw)/2, (height-th)/2
		for y := 0; y < th; y++ {
			copy(out.Pix[(oy+y)*out.Stride+ox*4:(oy+y)*out.Stride+(ox+tw)*4], inner.Pix[y*inner.Stride:y*inner.Stride+tw*4])
		}
		st.Crop = [4]int{0, 0, src.w, src.h}
	default:
		return nil, st, fmt.Errorf("unknown fit %q", fit)
	}
	png, err := encodePNG(out)
	return png, st, err
}

// Thumbnail returns a PNG whose longest side is at most edge pixels.
func Thumbnail(data []byte, edge int) ([]byte, error) {
	src, err := decodeRaster(data)
	if err != nil {
		return nil, err
	}
	s := math.Min(1, float64(edge)/float64(max(src.w, src.h)))
	w, h := max(1, int(math.Round(float64(src.w)*s))), max(1, int(math.Round(float64(src.h)*s)))
	return encodePNG(resample(src, 0, 0, src.w, src.h, w, h))
}

// SheetTile is one cell of the review sheet.
type SheetTile struct {
	PNG    []byte
	Status string // accepted | needs_review | failed
}

// ReviewSheet lays the tiles out in a grid, in order, each in a square cell
// with a status band below it (green accepted, amber needs review, red
// failed). Tile i of the sheet is asset i of the manifest.
func ReviewSheet(tiles []SheetTile, cell, columns int) ([]byte, error) {
	if len(tiles) == 0 {
		return nil, fmt.Errorf("review sheet needs at least one tile")
	}
	columns = max(1, min(columns, len(tiles)))
	rows := (len(tiles) + columns - 1) / columns
	const gap, band = 12, 8
	w := columns*(cell+gap) + gap
	h := rows*(cell+band+gap) + gap
	sheet := image.NewNRGBA(image.Rect(0, 0, w, h))
	for i := range sheet.Pix {
		sheet.Pix[i] = 255
	}
	bands := map[string]color.NRGBA{
		"accepted":     {46, 160, 67, 255},
		"needs_review": {214, 158, 46, 255},
		"failed":       {200, 50, 50, 255},
	}
	for i, t := range tiles {
		x0 := gap + (i%columns)*(cell+gap)
		y0 := gap + (i/columns)*(cell+band+gap)
		if len(t.PNG) > 0 {
			if src, err := decodeRaster(t.PNG); err == nil {
				s := math.Min(float64(cell)/float64(src.w), float64(cell)/float64(src.h))
				tw, th := max(1, int(float64(src.w)*s)), max(1, int(float64(src.h)*s))
				img := resample(src, 0, 0, src.w, src.h, tw, th)
				ox, oy := x0+(cell-tw)/2, y0+(cell-th)/2
				for y := 0; y < th; y++ {
					for x := 0; x < tw; x++ {
						sheet.SetNRGBA(ox+x, oy+y, img.NRGBAAt(x, y))
					}
				}
			}
		}
		c, ok := bands[t.Status]
		if !ok {
			c = bands["failed"]
		}
		for y := y0 + cell; y < y0+cell+band; y++ {
			for x := x0; x < x0+cell; x++ {
				sheet.SetNRGBA(x, y, c)
			}
		}
	}
	return encodePNG(sheet)
}
