import random

import pyrtl

try:
    from design import TopModule
    from ref import RefModule
except ImportError:
    from .design import TopModule
    from .ref import RefModule


DIRECTED_CASES = [
    (0x00, 0x00),
    (0x00, 0x70),
    (0x70, 0x70),
    (0x70, 0x90),
    (0x90, 0x70),
    (0x90, 0x90),
    (0x90, 0xFF),
]
RANDOM_CASE_COUNT = 100
RANDOM_SEED = 0


def build_cases(seed=RANDOM_SEED, random_case_count=RANDOM_CASE_COUNT):
    rng = random.Random(seed)
    cases = list(DIRECTED_CASES)

    for _ in range(random_case_count):
        value = rng.getrandbits(16)
        cases.append(((value >> 8) & 0xFF, value & 0xFF))

    return cases


def simulate_module(module_fn, cases):
    pyrtl.reset_working_block()

    a = pyrtl.Input(bitwidth=8, name="a")
    b = pyrtl.Input(bitwidth=8, name="b")
    s_wire, overflow_wire = module_fn(a, b)

    s = pyrtl.Output(bitwidth=8, name="s")
    overflow = pyrtl.Output(bitwidth=1, name="overflow")
    s <<= s_wire
    overflow <<= overflow_wire

    sim = pyrtl.Simulation()
    results = []

    for a_val, b_val in cases:
        sim.step({"a": a_val, "b": b_val})
        results.append(
            {
                "a": a_val,
                "b": b_val,
                "s": sim.inspect("s"),
                "overflow": sim.inspect("overflow"),
            }
        )

    return results


def compare_modules(cases):
    dut_results = simulate_module(TopModule, cases)
    ref_results = simulate_module(RefModule, cases)

    mismatches = []
    for index, (dut_result, ref_result) in enumerate(zip(dut_results, ref_results)):
        if (
            dut_result["s"] != ref_result["s"]
            or dut_result["overflow"] != ref_result["overflow"]
        ):
            mismatches.append(
                {
                    "index": index,
                    "dut": dut_result,
                    "ref": ref_result,
                }
            )

    return mismatches


def format_result(result):
    return (
        f"a=0x{result['a']:02x}, "
        f"b=0x{result['b']:02x}, "
        f"s=0x{result['s']:02x}, "
        f"overflow={result['overflow']}"
    )


def main():
    cases = build_cases()
    mismatches = compare_modules(cases)

    if not mismatches:
        print("Hint: Output 's' has no mismatches.")
        print("Hint: Output 'overflow' has no mismatches.")
        print(f"Hint: Total mismatched samples is 0 out of {len(cases)} samples")
        print(f"Mismatches: 0 in {len(cases)} samples")
        return 0

    s_mismatches = [mismatch for mismatch in mismatches if mismatch["dut"]["s"] != mismatch["ref"]["s"]]
    overflow_mismatches = [
        mismatch
        for mismatch in mismatches
        if mismatch["dut"]["overflow"] != mismatch["ref"]["overflow"]
    ]

    if s_mismatches:
        print(
            "Hint: Output 's' has "
            f"{len(s_mismatches)} mismatches. First mismatch occurred at sample "
            f"{s_mismatches[0]['index']}."
        )
    else:
        print("Hint: Output 's' has no mismatches.")

    if overflow_mismatches:
        print(
            "Hint: Output 'overflow' has "
            f"{len(overflow_mismatches)} mismatches. First mismatch occurred at sample "
            f"{overflow_mismatches[0]['index']}."
        )
    else:
        print("Hint: Output 'overflow' has no mismatches.")

    print(
        f"Hint: Total mismatched samples is {len(mismatches)} out of {len(cases)} samples"
    )
    print(f"Mismatches: {len(mismatches)} in {len(cases)} samples")

    for mismatch in mismatches[:10]:
        print(
            f"Sample {mismatch['index']}: "
            f"dut({format_result(mismatch['dut'])}) "
            f"ref({format_result(mismatch['ref'])})"
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
