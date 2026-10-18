# 3D model generators

These scripts build the meshes in `frontend/public/models/`. You only need them if you want to change the shapes.

```bash
pip install numpy scipy scikit-image
cd frontend/scripts/body
python make_body.py ../../public/models          # body-male.bin, body-female.bin, body-regions.json
python make_heart.py ../../public/models         # heart-points.json
python make_lena.py ../../public/models          # lena-mesh.json (Lena, low-poly wireframe; needs pyfqmr)
```

Each shape is a signed distance field: muscles (or heart chambers, or Lena's features) are smoothly blended
capsules and ellipsoids, turned into a surface with marching cubes. Every vertex keeps the name of the muscle it
belongs to, its fibre direction, a tendon amount and baked ambient occlusion, which the app's shader uses.
