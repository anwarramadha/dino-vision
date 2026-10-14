# Dino Vision Project Summary

## Goal

`dino-vision` controls the Chrome Dino game with Python. The agent captures the game frame, detects obstacles with a custom YOLOv8 model, predicts obstacle movement, and sends `jump` or `duck` through Chrome DevTools Protocol (CDP).

The current setup runs from WSL while Chrome runs on Windows. CDP is used because desktop-level input and capture libraries do not reliably control or capture a native Windows Chrome window from WSL.

## Runtime Pipeline

```text
Chrome Dino tab
  -> CDP screenshot capture
  -> Crop obstacle ROI
  -> YOLOv8 detection
  -> Multi-object tracking
  -> Speed and time-to-collision prediction
  -> Jump or duck through CDP keyboard event
```

Main entry point:

```bash
python scripts/run_agent.py --start-game --log-interval 0.2
```

## Capture and Control

### Chrome DevTools Protocol

The project uses CDP for both capture and input:

- `Page.captureScreenshot` captures the Chrome Dino tab directly.
- `Input.dispatchKeyEvent` sends `Space` for start/jump and `ArrowDown` for duck.
- `Emulation.setFocusEmulationEnabled` keeps Dino running while the terminal is focused.
- `Runner.getInstance()` provides game state, including whether the game is active, crashed, or Dino is jumping.

The agent skips inference and input when the game is in `GAME OVER` state. This prevents static Game Over cacti from being treated as active obstacles.

### Region of Interest

The current capture ROI excludes Dino itself to prevent it from being misclassified as a bird:

```yaml
capture:
  region: {left: 300, top: 650, width: 2280, height: 520}
```

The ROI starts to the right of Dino and retains the obstacle lane ahead of it.

## YOLOv8 Detection

The model is loaded from:

```yaml
detector:
  model_path: models/dino-yolo.pt
  confidence: 0.45
  image_size: 416
  inference_threads: 4
  classes: [cactus, bird]
```

`image_size: 416` is important. At `320`, the cactus became too small inside the wide ROI and the model returned no detection. The same frame successfully detected cactus at `416`, `512`, and `640`.

`scripts/test_detector.py` is used to validate the model without controlling the game. It saves a preview with red bounding boxes and confidence labels.

## Custom Dataset and Training

The YOLOv8 model was trained using a custom Chrome Dino dataset created for this project.

1. Gameplay was recorded from the screen while Chrome Dino was running.
2. Frames were selected and uploaded to Roboflow.
3. Approximately 300 images were annotated manually with obstacle bounding boxes.
4. Annotation classes were:
   - `cactus`
   - `bird`
5. Roboflow generated a versioned YOLOv8 dataset with train, validation, and test splits.
6. The dataset was downloaded from Roboflow and trained in Google Colab using the project training script.

The training script is designed to run independently in Colab:

```text
training/train_yolo_colab.py
```

It downloads the selected Roboflow dataset version, trains a YOLOv8 model, and saves the best model to Google Drive. The exported model is then placed in the local project as:

```text
models/dino-yolo.pt
```

The dataset is not committed to Git. Roboflow is used for annotation, dataset versioning, and dataset export, while Google Colab provides the training environment.

## Jump and Duck Policy

### Multi-Object Tracking

The agent does not use only one global obstacle anymore. Each detected cactus or bird has its own track containing:

- Track ID
- Label
- Position history across multiple frames
- Estimated horizontal speed
- Predicted position
- Estimated time-to-collision (TTC)
- `ready` or `handled` state

After an action is sent for one obstacle, only that track is marked `handled`. Other tracks remain available for future decisions.

### Predictive Time-to-Collision

Obstacle speed is estimated from a four-frame history:

```text
speed = horizontal position change / elapsed time
```

The policy predicts where the obstacle will be after inference and input latency:

```text
predicted_x = observed_x - speed * (inference_age + input_latency)
effective_ttc = observed_x / speed - inference_age - input_latency
```

This is necessary because a screenshot may already be hundreds of milliseconds old by the time the keyboard event is sent.

### Standard Obstacle Decisions

```yaml
policy:
  jump_ttc_seconds: 0.32
  duck_ttc_seconds: 0.28
  emergency_distance_ratio: 0.06
```

- Cactus and high birds trigger `jump` when their effective TTC is below the adjusted jump limit.
- Low birds trigger `duck` when their effective TTC is below the duck limit.
- An emergency distance trigger handles objects that are already too close before speed can be estimated.
- A second `Space` event is not sent while Dino is already jumping.

### Cactus Size Adjustment

Larger cactus bounding boxes use a smaller TTC limit, so they trigger closer to Dino:

```yaml
cactus_size_ttc_reduction: 0.35
cactus_reference_height_ratio: 0.20
cactus_reference_width_ratio: 0.12
```

The policy calculates a size score from normalized bounding-box height and width. A small cactus uses a TTC limit closer to the base `jump_ttc_seconds`, while a large cactus uses a reduced limit.

### Clustered Obstacles

When two obstacles are close together, the front obstacle receives an earlier trigger to give Dino enough airtime to clear the group:

```yaml
obstacle_cluster_gap_ratio: 0.25
cluster_ttc_bonus_seconds: 0.12
```

If a following obstacle is within 25% of the ROI width, `0.12s` is added to the TTC limit of the front obstacle.

## Optimizations Applied

### Fast CDP Capture

Capture uses JPEG rather than PNG:

```yaml
capture:
  image_format: jpeg
  jpeg_quality: 80
  optimize_for_speed: true
```

JPEG is suitable for the high-contrast Dino game and reduces browser encoding cost. PNG can still be used when collecting lossless training data.

### CPU Thread Tuning

PyTorch is configured with four inference threads:

```yaml
detector:
  inference_threads: 4
```

This was the most stable setting on the available eight-core Intel CPU.

### Debug Telemetry

`--log-interval` prints detailed diagnostics:

```text
latency_ms(state=1 capture=120 inference=24 policy=0 decision_age=24 input=5 verify=1 save=0)
```

Field meanings:

- `state`: CDP game-state query.
- `capture`: CDP screenshot time.
- `inference`: YOLO model execution.
- `policy`: tracking and action decision time.
- `decision_age`: time from completed capture to the decision.
- `input`: CDP keyboard event time.
- `verify`: CDP query that verifies Dino state after input.
- `save`: debug preview PNG write time.

Use `--save-interval` to save annotated previews. The preview includes bounding boxes, proposed action, resulting action, speed, predicted position, TTC, and latency-related values.

## Current Bottleneck

The main bottleneck is Chrome CDP screenshot capture, not the action policy.

Measured steady-state values after JPEG optimization:

```text
CDP capture: approximately 116-161ms
PyTorch inference: approximately 17-42ms in steady state
CDP input: approximately 5ms
```

Capture latency is significant because Chrome must render and encode a full tab screenshot before the ROI is cropped locally. At obstacle speeds near `1000px/s`, a `120ms` capture delay alone represents roughly `120px` of obstacle movement.

## OpenVINO Result

OpenVINO was exported from the active YOLOv8 model:

```bash
yolo export model=models/dino-yolo.pt format=openvino imgsz=416
```

An earlier OpenVINO artifact was exported at `320x320` and returned zero detections. Re-exporting at `416x416` fixed detection parity with the PyTorch model.

However, OpenVINO was slower in this environment:

```text
PyTorch .pt:            average 25ms, p95 36ms, max 42ms
OpenVINO CPU:           average 47ms, p95 64ms, max 76ms
```

For this project, `models/dino-yolo.pt` is therefore the active runtime model.

## Why OpenVINO Was Slower

OpenVINO is not guaranteed to outperform PyTorch for a small single-frame model:

- YOLOv8 nano is small enough that OpenVINO runtime and conversion overhead matter.
- PyTorch already uses optimized CPU kernels effectively for this model.
- The workload is batch size 1, where OpenVINO optimization gains can be smaller.
- The project runs under WSL, which can add runtime overhead.
- OpenVINO only exposes `CPU` in this environment; Intel GPU and NPU are not available in WSL.

The available OpenVINO devices are:

```text
['CPU']
```

Running native Windows Python with the Intel GPU plugin may provide a different result, but it has not been tested in this project.

## Recommended Commands

Validate detection only:

```bash
python scripts/test_detector.py
```

Run the agent with text diagnostics:

```bash
python scripts/run_agent.py --start-game --log-interval 0.2
```

Run with annotated preview frames:

```bash
python scripts/run_agent.py --start-game --log-interval 0.2 --save-interval 0.2
```
