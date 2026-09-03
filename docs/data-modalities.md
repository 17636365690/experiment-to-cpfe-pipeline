# Data modalities and conversion rules

## Tables and time series

CSV, delimited TXT, and JSON record arrays require an explicit target-to-source column map and units. Typical records include force, displacement, stress, strain, temperature, time, cycle, and control mode. Mechanical curves are calibration or validation evidence unless a user separately supplies a complete material model and parameters.

## EBSD and orientation maps

Text `.ang` and `.ctf` inputs use explicit coordinate, phase, orientation, and quality-field mappings. `.osc`, `.crc`, `.cpr`, vendor HDF5, h5ebsd, and DREAM.3D files are registered in their native layout and require a named layout profile before semantic parsing. Euler convention, angle unit, quaternion order, sample frame, and crystal symmetry are mandatory.

## Images and DIC/DVC fields

Reference/deformed images remain image assets. Point fields preserve coordinate columns and displacement or strain components. Regular grids additionally require origin, spacing, axis order, units, and coordinate frame. Interpolation, registration, smoothing, and resampling are recorded as lossy transformations.

## CT and voxel grids

NumPy, explicitly addressed HDF5 datasets, and tiny JSON synthetic fixtures preserve origin, spacing, axis order, dtype, shape, units, and frame. Segmentation and voxel-to-mesh conversion create new child assets; raw scans are not overwritten.

## Meshes and microstructure mappings

Mesh assets preserve node and element IDs, connectivity, element type, regions, sets, and coordinate units. Grain-to-element mappings must reference existing grain IDs. A mesh does not imply a material model or boundary conditions.

## Grain graphs and field sequences

Grain graphs use node features, edge indices, optional edge features, and graph-level metadata. Field sequences preserve step, frame, increment, location, component, and original field name. NPZ and PyG exports retain the canonical HDF5 hash.

## Solver formats

Abaqus `.inp`, `.odb`, `.sta`, `.dat`, and `.msg` are distinct evidence artifacts. DAMASK `material.yaml`, `numerics.yaml`, VTI/VTK, and HDF5 remain backend-specific assets. Neper/FEPX `.tess`, `.tesr`, `.msh`, `.ori`, and `.sim` are registered without imposing Abaqus semantics.
