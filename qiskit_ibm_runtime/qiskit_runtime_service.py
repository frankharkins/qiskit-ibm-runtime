# This code is part of Qiskit.
#
# (C) Copyright IBM 2022.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Qiskit runtime service."""

import json
import logging
import traceback
import warnings
from datetime import datetime
from collections import OrderedDict
from typing import Dict, Callable, Optional, Union, List, Any, Type, Sequence

from qiskit.providers.backend import BackendV1 as Backend
from qiskit.providers.provider import ProviderV1 as Provider
from qiskit.providers.exceptions import QiskitBackendNotFoundError
from qiskit.providers.providerutils import filter_backends
from qiskit.providers.models import (
    PulseBackendConfiguration,
    QasmBackendConfiguration,
)

from qiskit_ibm_provider.proxies import ProxyConfiguration
from qiskit_ibm_provider.utils.hgp import to_instance_format, from_instance_format
from qiskit_ibm_provider.utils.backend_decoder import configuration_from_server_data
from qiskit_ibm_runtime import ibm_backend

from .utils.utils import validate_job_tags
from .accounts import AccountManager, Account, ChannelType
from .api.clients import AuthClient, VersionClient
from .api.clients.runtime import RuntimeClient
from .api.exceptions import RequestsApiError
from .constants import QISKIT_IBM_RUNTIME_API_URL
from .exceptions import IBMNotAuthorizedError, IBMInputValueError, IBMAccountError
from .exceptions import (
    IBMRuntimeError,
    RuntimeProgramNotFound,
    RuntimeJobNotFound,
)
from .hub_group_project import HubGroupProject  # pylint: disable=cyclic-import
from .utils.result_decoder import ResultDecoder
from .runtime_job import RuntimeJob
from .utils import RuntimeDecoder, to_python_identifier
from .api.client_parameters import ClientParameters
from .runtime_options import RuntimeOptions
from .ibm_backend import IBMBackend

from .fake_provider import FakeProviderForBackendV2

logger = logging.getLogger(__name__)

SERVICE_NAME = "runtime"


class QiskitRuntimeService(FakeProviderForBackendV2):
    """Class for interacting with the Qiskit Runtime service.

    Qiskit Runtime is a new architecture offered by IBM Quantum that
    streamlines computations requiring many iterations. These experiments will
    execute significantly faster within its improved hybrid quantum/classical
    process.

    A sample workflow of using the runtime service::

        from qiskit_ibm_runtime import QiskitRuntimeService, Session, Sampler, Estimator, Options
        from qiskit.test.reference_circuits import ReferenceCircuits
        from qiskit.circuit.library import RealAmplitudes
        from qiskit.quantum_info import SparsePauliOp

        # Initialize account.
        service = QiskitRuntimeService()

        # Set options, which can be overwritten at job level.
        options = Options(optimization_level=1)

        # Prepare inputs.
        bell = ReferenceCircuits.bell()
        psi = RealAmplitudes(num_qubits=2, reps=2)
        H1 = SparsePauliOp.from_list([("II", 1), ("IZ", 2), ("XI", 3)])
        theta = [0, 1, 1, 2, 3, 5]

        with Session(service=service, backend="ibmq_qasm_simulator") as session:
            # Submit a request to the Sampler primitive within the session.
            sampler = Sampler(session=session, options=options)
            job = sampler.run(circuits=bell)
            print(f"Sampler results: {job.result()}")

            # Submit a request to the Estimator primitive within the session.
            estimator = Estimator(session=session, options=options)
            job = estimator.run(
                circuits=[psi], observables=[H1], parameter_values=[theta]
            )
            print(f"Estimator results: {job.result()}")

    The example above uses the dedicated :class:`~qiskit_ibm_runtime.Sampler`
    and :class:`~qiskit_ibm_runtime.Estimator` classes. You can also
    use the :meth:`run` method directly to invoke a Qiskit Runtime program.

    If the program has any interim results, you can use the ``callback``
    parameter of the :meth:`run` method to stream the interim results.
    Alternatively, you can use the :meth:`RuntimeJob.stream_results` method to stream
    the results at a later time, but before the job finishes.

    The :meth:`run` method returns a
    :class:`RuntimeJob` object. You can use its
    methods to perform tasks like checking job status, getting job result, and
    canceling job.
    """

    global_service = None

    def __init__(
        self,
        channel: Optional[ChannelType] = None,
        token: Optional[str] = None,
        url: Optional[str] = None,
        filename: Optional[str] = None,
        name: Optional[str] = None,
        instance: Optional[str] = None,
        proxies: Optional[dict] = None,
        verify: Optional[bool] = None,
        channel_strategy: Optional[str] = None,
    ) -> None:
        """QiskitRuntimeService constructor
        """
        super().__init__()
