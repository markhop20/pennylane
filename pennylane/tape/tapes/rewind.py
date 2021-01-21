# Copyright 2018-2021 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Quantum tape for implementing the gradient method outlined in https://arxiv.org/abs/2009.02823,
referred to here as the "rewind" method.
"""
# pylint: disable=protected-access
import pennylane as qml
from pennylane.devices import DefaultMixed
from .jacobian_tape import JacobianTape
import numpy as np


class RewindTape(JacobianTape):
    r"""TODO
    """

    def jacobian(self, device, params=None, **options):
        """TODO

        Args:
            device:
            params:
            **options:

        Returns:
        """

        # The rewind tape only support differentiating expectation values of observables for now.
        for m in self.measurements:
            if (
                m.return_type is not qml.operation.Expectation
            ):
                raise ValueError(
                    f"The {m.return_type.value} return type is not supported with the rewind gradient method"
                )

        method = options.get("method", "analytic")

        if method == "device":
            # Using device mode; simply query the device for the Jacobian
            return self.device_pd(device, params=params, **options)
        elif method == "numeric":
            raise ValueError("RewindTape does not support numeric differentiation")

        if not device.capabilities().get("returns_state") or isinstance(device, DefaultMixed) \
            or not hasattr(device, "_apply_operation"):
            # TODO: consider renaming returns_state to, e.g., uses_statevector
            # TODO: consider adding a capability for mixed/pure state
            # TODO: consider adding capability for apply_operation
            raise qml.QuantumFunctionError("The rewind gradient method is only supported on statevector-based devices")

        # Perform the forward pass
        # TODO: Could we use lower-level like device.apply, since we just need the state?
        self.execute(device, params=params)
        phi = device._state  # TODO: Do we need dev._state or dev.state?

        lambdas = [device._apply_operation(phi, obs) for obs in self.observables]

        jac = np.zeros((len(lambdas), len(self.trainable_params)))

        expanded_ops = []
        for op in reversed(self.operations):
            if op.num_params > 1:
                if op.inverse:
                    raise qml.QuantumFunctionError(f"Applying the inverse is not supported for {op.name}")
                ops = op.decomposition(*op.parameters, wires=op.wires)
                if not all(op.generator[0] is not None and op.num_params == 1 for op in ops):
                    raise qml.QuantumFunctionError(f"The {op.name} operation cannot be decomposed into single-parameter operations with a valid generator")
                expanded_ops.extend(reversed(ops))
            else:
                expanded_ops.append(op)

        param_number = 0
        for op in expanded_ops:

            if op.grad_method:
                # TODO: Only use a matrix when necessary
                d_op_matrix = operator_derivative(op)

            op.inv()
            phi = device._apply_operation(phi, op)

            if op.grad_method:
                mu = device._apply_unitary(phi, d_op_matrix, op.wires)

                jac_column = np.array([2 * np.real(dot_product(lambda_, mu)) for lambda_ in lambdas])
                jac[:, param_number] = jac_column
                param_number += 1

            lambdas = [device._apply_operation(lambda_, op) for lambda_ in lambdas]
            op.inv()

        return np.flip(jac, axis=1)


def dot_product(a, b):
    """TODO"""
    return np.sum(a.conj() * b)


def operator_derivative(operator):
    """TODO"""
    generator, prefactor = operator.generator

    if generator is None:
        raise ValueError(f"Operator {operator.name} does not have a generator")
    if not isinstance(generator, np.ndarray):
        generator = generator.matrix

    if operator.inverse:
        prefactor *= -1
        generator = generator.conj().T

    return 1j * prefactor * generator @ operator.matrix








