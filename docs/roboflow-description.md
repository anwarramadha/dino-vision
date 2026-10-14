# Roboflow Description

## Dataset Name

Chrome Dino Obstacle Detection

## Description

This dataset contains screenshots independently collected from the Chrome Dino game (`chrome://dino`). Its purpose is to train a YOLO model to detect obstacles in real time before the Dino character reaches them, allowing a Python agent to decide whether to jump or duck.

Each image is captured directly from the game area through the Chrome DevTools Protocol and annotated with bounding boxes for every visible obstacle. The dataset includes variations in obstacle position, distance from Dino, game speed, day and night modes, single and grouped cacti, and birds at different heights.

## Annotation Classes

- `cactus`: All cactus variations, including single cacti and cactus groups.
- `bird`: Flying bird obstacles at different heights.

The `dino` class is not annotated because the model focuses on obstacle detection. Dino's position is considered relatively fixed within the calibrated screenshot area.

## Usage

The dataset is exported in YOLOv8 format and used to train an object-detection model. The trained model is used by the `dino-vision` project in the following pipeline:

```text
Game screenshot -> YOLO detection -> Obstacle distance estimation -> Jump or duck
```

## License and Data Source

All screenshots are independently collected for learning and computer vision experimentation. Chrome Dino game visual assets belong to Google Chrome. This dataset is not intended for commercial use or for redistributing game assets separately.
