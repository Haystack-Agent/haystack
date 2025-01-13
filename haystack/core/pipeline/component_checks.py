# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List

from haystack.core.component.types import _empty, InputSocket

_NO_OUTPUT_PRODUCED = _empty


def can_component_run(component: Dict, inputs: Dict) -> bool:
    """
    Checks if the component can run, given the current state of its inputs.
    A component needs to pass two gates so that it is ready to run:
    1. It has received all mandatory inputs.
    2. It has received a trigger.
    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    received_all_mandatory_inputs = are_all_mandatory_sockets_ready(component, inputs)
    received_trigger = has_any_trigger(component, inputs)

    return received_all_mandatory_inputs and received_trigger


def has_any_trigger(component: Dict, inputs: Dict) -> bool:
    """
    Checks if a component was triggered to execute.

    There are 3 triggers:
    1. A predecessor provided input to the component.
    2. Input to the component was provided from outside the pipeline (e.g. user input).
    3. The component does not receive input from any other components in the pipeline and `Pipeline.run` was called.

    A trigger can only cause a component to execute ONCE because:
    1. Components consume inputs from predecessors before execution (they are deleted).
    2. Inputs from outside the pipeline can only trigger a component when it is executed for the first time.
    3.  `Pipeline.run` can only trigger a component when it is executed for the first time.

    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    trigger_from_predecessor = any_predecessors_provided_input(component, inputs)
    trigger_from_user = has_user_input(inputs) and component["visits"] == 0
    trigger_without_inputs = can_not_receive_inputs_from_pipeline(component) and component["visits"] == 0

    return trigger_from_predecessor or trigger_from_user or trigger_without_inputs


def are_all_mandatory_sockets_ready(component: Dict, inputs: Dict) -> bool:
    """
    Checks if all mandatory sockets of a component have enough inputs for the component to execute.
    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    filled_mandatory_sockets = set()
    expected_mandatory_sockets = set()
    for socket_name, socket in component["input_sockets"].items():
        if socket.is_mandatory:
            socket_inputs = inputs.get(socket_name, [])
            expected_mandatory_sockets.add(socket_name)
            if is_socket_lazy_variadic(socket) and any_socket_input_received(socket_inputs):
                filled_mandatory_sockets.add(socket_name)
            elif has_socket_received_all_inputs(socket, socket_inputs):
                filled_mandatory_sockets.add(socket_name)

    return filled_mandatory_sockets == expected_mandatory_sockets


def any_predecessors_provided_input(component: Dict, inputs: Dict) -> bool:
    """
    Checks if a component received inputs from any predecessors.

    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    return any(
        any_socket_value_from_predecessor_received(inputs.get(socket_name, []))
        for socket_name in component["input_sockets"].keys()
    )


def any_socket_value_from_predecessor_received(socket_inputs: List[Dict[str, Any]]) -> bool:
    """
    Checks if a component socket received input from any predecessors.
    :param socket_inputs: Inputs for the component's socket.
    """
    # When sender is None, the input was provided from outside the pipeline.
    return any(inp["value"] != _NO_OUTPUT_PRODUCED and inp["sender"] is not None for inp in socket_inputs)


def has_user_input(inputs: Dict) -> bool:
    """
    Checks if a component has received input from outside the pipeline (e.g. user input).
    :param inputs: Inputs for the component.
    """
    return any(inp for socket in inputs.values() for inp in socket if inp["sender"] is None)


def can_not_receive_inputs_from_pipeline(component: Dict) -> bool:
    """
    Checks if a component can not receive inputs from any other components in the pipeline.
    :param: Component metadata and the component instance.
    """
    return all([len(sock.senders) == 0 for sock in component["input_sockets"].values()])


def all_socket_predecessors_executed(socket: InputSocket, socket_inputs: List[Dict]) -> bool:
    """
    Checks if all components connecting to an InputSocket have executed.
    :param: The InputSocket of a component.
    :param: socket_inputs: Inputs for the socket.
    """
    expected_senders = set(socket.senders)
    executed_senders = {inp["sender"] for inp in socket_inputs if inp["sender"] is not None}

    return expected_senders == executed_senders


def any_socket_input_received(socket_inputs: List[Dict]) -> bool:
    """
    Checks if a socket has received any input from any other components in the pipeline or from outside the pipeline.
    :param socket_inputs: Inputs for the socket.
    """
    return any(inp["value"] != _NO_OUTPUT_PRODUCED for inp in socket_inputs)


def has_lazy_variadic_socket_received_all_inputs(socket: InputSocket, socket_inputs: List[Dict]) -> bool:
    """
    Checks if a lazy variadic socket has received all expected inputs from other components in the pipeline.
    :param socket: The InputSocket of a component.
    :param socket_inputs: Inputs for the socket.
    """
    expected_senders = set(socket.senders)
    actual_senders = {
        sock["sender"] for sock in socket_inputs if sock["value"] != _NO_OUTPUT_PRODUCED and sock["sender"] is not None
    }

    return expected_senders == actual_senders


def is_socket_lazy_variadic(socket: InputSocket) -> bool:
    """
    Checks if an InputSocket is a lazy variadic socket.
    :param socket: The InputSocket of a component.
    """
    return socket.is_variadic and not socket.is_greedy


def has_socket_received_all_inputs(socket: InputSocket, socket_inputs: List[Dict]) -> bool:
    """
    Checks if a socket has received all expected inputs.
    :param socket: The InputSocket of a component.
    :param socket_inputs: Inputs for the socket.
    """
    # No inputs received for the socket, it is not filled.
    if len(socket_inputs) == 0:
        return False

    # The socket is greedy variadic and at least one input was produced, it is complete.
    if (
        socket.is_variadic
        and socket.is_greedy
        and len(socket_inputs) > 0
        and any([sock["value"] != _NO_OUTPUT_PRODUCED for sock in socket_inputs])
    ):
        return True

    # The socket is lazy variadic and all expected inputs were produced.
    if is_socket_lazy_variadic(socket) and has_lazy_variadic_socket_received_all_inputs(socket, socket_inputs):
        return True

    # The socket is not variadic and the only expected input is complete.
    if not socket.is_variadic and socket_inputs[0]["value"] != _NO_OUTPUT_PRODUCED:
        return True

    return False


def all_predecessors_executed(component: Dict, inputs: Dict) -> bool:
    """
    Checks if all predecessors of a component have executed.
    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    return all(
        all_socket_predecessors_executed(socket, inputs.get(socket_name, []))
        for socket_name, socket in component["input_sockets"].items()
    )


def are_all_lazy_variadic_sockets_resolved(component: Dict, inputs: Dict) -> bool:
    """
    Checks if the final state for all lazy variadic sockets of a component is resolved.
    Either because all inputs were received, or because all predecessors executed.
    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    for socket_name, socket in component["input_sockets"].items():
        if is_socket_lazy_variadic(socket):
            socket_inputs = inputs.get(socket_name, [])
            if not (
                has_lazy_variadic_socket_received_all_inputs(socket, socket_inputs)
                or all_socket_predecessors_executed(socket, socket_inputs)
            ):
                return False

    return True


def is_any_greedy_socket_ready(component: Dict, inputs: Dict) -> bool:
    """
    Checks if the component has any greedy socket that is ready to run.
    :param component: Component metadata and the component instance.
    :param inputs: Inputs for the component.
    """
    for socket_name, socket in component["input_sockets"].items():
        if socket.is_greedy and has_socket_received_all_inputs(socket, inputs.get(socket_name, [])):
            return True

    return False
