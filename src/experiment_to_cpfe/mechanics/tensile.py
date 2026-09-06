"""Small-strain bilinear tension calibration and nodal reaction reduction."""

import numpy as np


def bilinear_stress(strain, modulus, yield_stress, hardening_modulus):
    """Monotonic uniaxial J2 response with linear isotropic plastic hardening."""
    if not np.isfinite([modulus, yield_stress, hardening_modulus]).all() or min(modulus, yield_stress, hardening_modulus) <= 0:
        raise ValueError('positive finite material parameters required')
    strain = np.asarray(strain, dtype=float)
    if not np.isfinite(strain).all() or (strain < 0).any():
        raise ValueError('tensile strain must be finite and nonnegative')
    elastic = modulus * strain
    plastic = yield_stress + modulus * hardening_modulus / (modulus + hardening_modulus) * (strain - yield_stress / modulus)
    return np.minimum(elastic, plastic)


def regression_metrics(reference, prediction):
    reference, prediction = np.asarray(reference, float), np.asarray(prediction, float)
    if reference.shape != prediction.shape or not reference.size or not np.isfinite(reference).all() or not np.isfinite(prediction).all():
        raise ValueError('metrics require aligned nonempty finite arrays')
    residual = prediction - reference
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    scale = float(np.max(np.abs(reference)))
    variance = float(np.sum((reference - reference.mean()) ** 2))
    return {'rmse': rmse, 'mae': float(np.mean(np.abs(residual))), 'bias': float(np.mean(residual)),
            'max_abs_error': float(np.max(np.abs(residual))), 'nrmse': rmse / scale if scale else None,
            'r2': 1 - float(np.sum(residual ** 2)) / variance if variance else None, 'count': int(reference.size)}


def fit_bilinear(strain, stress, *, modulus, yield_bounds, hardening_bounds):
    from scipy.optimize import least_squares
    strain, stress = np.asarray(strain, float), np.asarray(stress, float)
    if strain.ndim != 1 or stress.shape != strain.shape or len(strain) < 4 or not np.isfinite(strain).all() or not np.isfinite(stress).all() or (np.diff(strain) <= 0).any() or (strain < 0).any():
        raise ValueError('calibration requires ordered finite tensile strain and matching stress')
    lower = np.array([yield_bounds[0], hardening_bounds[0]], float)
    upper = np.array([yield_bounds[1], hardening_bounds[1]], float)
    if not np.isfinite([*lower, *upper, modulus]).all() or modulus <= 0 or (lower <= 0).any() or (upper <= lower).any():
        raise ValueError('calibration bounds and modulus must be positive and ordered')
    optimum = least_squares(lambda p: bilinear_stress(strain, modulus, *np.exp(p)) - stress,
                            (np.log(lower) + np.log(upper)) / 2,
                            bounds=(np.log(lower), np.log(upper)), xtol=1e-12, ftol=1e-12, gtol=1e-12)
    if not optimum.success:
        raise ValueError('bilinear calibration did not converge')
    yield_stress, hardening = np.exp(optimum.x)
    return {'modulus': float(modulus), 'yield_stress': float(yield_stress), 'hardening_modulus': float(hardening),
            'metrics': regression_metrics(stress, bilinear_stress(strain, modulus, yield_stress, hardening)),
            'method': 'fixed E; bounded least squares for yield stress and linear plastic modulus'}


def reduce_axial_records(records, *, step, instance, top_nodes, axis, area, length, force_unit, length_unit):
    """Sum unique nodal reactions and average the prescribed end displacement."""
    if axis not in (1, 2, 3) or not np.isfinite([area, length]).all() or min(area, length) <= 0:
        raise ValueError('positive geometry and an explicit axis are required')
    if not top_nodes or len(set(top_nodes)) != len(top_nodes):
        raise ValueError('unique nonempty end-face node IDs required')
    chosen = [r for r in records if r.get('step') == step and r.get('instance') == instance]
    frames = sorted({int(r['frame']) for r in chosen})
    if not frames:
        raise ValueError('selected step and instance have no records')
    wanted = {('U', f'U{axis}'): length_unit, ('RF', f'RF{axis}'): force_unit}
    lookup = {}
    for row in chosen:
        field = (row.get('field'), row.get('component'))
        if field not in wanted or str(row.get('position')).lower() != 'nodal' or row.get('node_label') not in top_nodes:
            continue
        key = (int(row['frame']), field[0], row['node_label'])
        if key in lookup or row.get('unit') != wanted[field] or not np.isfinite(float(row['value'])):
            raise ValueError('axial reduction requires unique finite nodal values in declared units')
        lookup[key] = (float(row['value']), float(row['frame_time']))
    output = {k: [] for k in ('frame', 'time', 'displacement', 'force', 'strain', 'stress')}
    for frame in frames:
        try:
            displacements = [lookup[(frame, 'U', n)][0] for n in top_nodes]
            forces = [lookup[(frame, 'RF', n)][0] for n in top_nodes]
            times = [lookup[(frame, f, n)][1] for n in top_nodes for f in ('U', 'RF')]
        except KeyError as exc:
            raise ValueError('missing end-face nodal record') from exc
        if not np.isfinite(times).all() or not np.allclose(times, times[0], rtol=0, atol=1e-10) or not np.allclose(displacements, displacements[0], rtol=1e-6, atol=1e-10):
            raise ValueError('end-face time or prescribed displacement is inconsistent')
        displacement, force = float(np.mean(displacements)), float(np.sum(forces))
        for key, value in zip(output, (frame, times[0], displacement, force, displacement / length, force / area)):
            output[key].append(value)
    return {k: np.asarray(v) for k, v in output.items()}
