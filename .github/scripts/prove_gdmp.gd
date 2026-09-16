extends SceneTree
## Run the freshly built GDMP inside a real Godot binary and write down what
## came back. `prove_gdmp.py detect` asserts against the file this writes.
##
## ⚠️ **This script asserts NOTHING.** It measures and records, and the
## assertions live in one place in the python so a change to what counts as a
## pass cannot hide in a GDScript branch. It exits 0 even when detection fails,
## because "the detector found nothing" is a RESULT that the checker must be
## allowed to see and reject -- a probe that fails the job itself would report
## the same thing for "MediaPipe is broken" and "I could not read the image".
##
## Usage:
##   godot --headless --path <project> -s prove_gdmp.gd -- <model> <portrait> <out.json>

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var model_path := args[0] if args.size() > 0 else "face_landmarker.task"
	var portrait_path := args[1] if args.size() > 1 else "portrait.jpg"
	var out_path := args[2] if args.size() > 2 else "gdmp_result.json"

	var out := {
		"godot": Engine.get_version_info(),
		"mediapipe_classes": 0,
		"portrait_faces": -1,
		"blank_faces": null,
		"blendshape_names": [],
		"top": [],
		"has_transform": false,
		"errors": [],
	}

	# 1. Did the extension load at all?
	var mp := []
	for c in ClassDB.get_class_list():
		if str(c).begins_with("MediaPipe"):
			mp.append(str(c))
	out["mediapipe_classes"] = mp.size()
	if mp.is_empty():
		out["errors"].append("no MediaPipe classes registered: the extension did not load")
		_write(out_path, out)
		quit()
		return

	# ⚠️ NOT `:=`. The helper returns an untyped value, and inferring from it
	# is a PARSE error, which makes the whole script fail to load rather than
	# fail a check -- the shape that makes a test file invisible to a runner.
	var lm = _make_landmarker(model_path, out)
	if lm == null:
		_write(out_path, out)
		quit()
		return

	# 2. The portrait. A real face, so a real result.
	var img := Image.new()
	var err := img.load(portrait_path)
	if err != OK:
		out["errors"].append("could not load portrait %s (err %d)" % [portrait_path, err])
		_write(out_path, out)
		quit()
		return
	out["portrait_size"] = [img.get_width(), img.get_height()]
	var mpi = MediaPipeImage.new()
	mpi.set_image(img)
	var t0 := Time.get_ticks_msec()
	var res = lm.detect(mpi, Rect2(), 0)
	out["detect_ms"] = Time.get_ticks_msec() - t0
	if res == null:
		out["errors"].append("detect() returned null on the portrait")
		_write(out_path, out)
		quit()
		return

	var shapes = res.get_face_blendshapes()
	out["portrait_faces"] = shapes.size()
	out["has_transform"] = res.has_facial_transformation_matrixes() \
		and res.get_facial_transformation_matrixes().size() > 0
	if shapes.size() > 0:
		var cats = shapes[0].get_categories()
		var rows := []
		for c in cats:
			out["blendshape_names"].append(c.get_category_name())
			rows.append([c.get_category_name(), c.get_score()])
		rows.sort_custom(func(a, b): return a[1] > b[1])
		out["top"] = rows.slice(0, 8)

	# 3. 🔴 The control: flat grey has no face in it. If this finds one, every
	# number above is worthless, and it is worthless in the permissive direction.
	var blank := Image.create(640, 480, false, Image.FORMAT_RGB8)
	blank.fill(Color(0.5, 0.5, 0.5))
	var blank_mpi = MediaPipeImage.new()
	blank_mpi.set_image(blank)
	var blank_res = lm.detect(blank_mpi, Rect2(), 0)
	out["blank_faces"] = 0 if blank_res == null else blank_res.get_face_blendshapes().size()

	_write(out_path, out)
	quit()


func _make_landmarker(model_path: String, out: Dictionary):
	if not FileAccess.file_exists(model_path):
		out["errors"].append("model not found at %s" % model_path)
		return null
	var base = MediaPipeTaskBaseOptions.new()
	base.model_asset_path = model_path
	var lm = MediaPipeFaceLandmarker.new()
	# ⚠️ running_mode 1 is IMAGE. Zero is not "the first one" -- it is the unset
	# value, and passing it produces "Task is not initialized with the image
	# mode. Current running mode: unknown mode", which is a refusal rather than a
	# default. Measured 2026-09-16.
	lm.initialize(base, 1, 1, 0.5, 0.5, 0.5, true, true)
	return lm


func _write(path: String, data: Dictionary) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_error("could not write %s" % path)
		return
	f.store_string(JSON.stringify(data, "  "))
	f.close()
	print("wrote ", path)
	print(JSON.stringify(data))
