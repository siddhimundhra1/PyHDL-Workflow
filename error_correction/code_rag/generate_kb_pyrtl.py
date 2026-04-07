from __future__ import annotations

import ast
import csv
import re
import textwrap
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "knowledge_base"
OUTPUT_DIR = BASE_DIR / "kb_pyrtl"

SECTION_RE = re.compile(
    r"^\[(?P<name>[^\n]+?)\]:(?P<body>.*?)(?=^\[[^\n]+\]:|\Z)",
    re.MULTILINE | re.DOTALL,
)


def code(text: str) -> str:
    return textwrap.dedent(text).strip() + "\n"


SELECTED = [
    {"source": "Reduction.txt", "focus": "vector reduction and parity"},
    {"source": "7Vector1.txt", "focus": "vector slicing and packing"},
    {"source": "Vectorgates.txt", "focus": "bitwise and logical vector operations"},
    {"source": "Gates4.txt", "focus": "reduction-style boolean operations"},
    {"source": "Mux2to1.txt", "focus": "single-bit mux pattern"},
    {"source": "Mux_8_to_1.txt", "focus": "multi-input mux construction"},
    {"source": "Mux256to1.txt", "focus": "indexed bit selection"},
    {"source": "binary_decoder_2x4.txt", "focus": "small decoder pattern"},
    {"source": "binary_decoder_3x8.txt", "focus": "medium decoder pattern"},
    {"source": "binary_decoder_4x16.txt", "focus": "wide decoder pattern"},
    {"source": "dual_prioenc.txt", "focus": "priority encoding"},
    {"source": "dual_comparator.txt", "focus": "signed versus unsigned comparison"},
    {"source": "greater_than_4bit.txt", "focus": "comparator logic"},
    {"source": "adder.txt", "focus": "basic arithmetic"},
    {"source": "adder32.txt", "focus": "wide arithmetic with carry"},
    {"source": "carry_save_adder.txt", "focus": "multi-operand addition"},
    {"source": "carry_look_ahead_adder.txt", "focus": "adder family coverage"},
    {"source": "bcd_adder.txt", "focus": "single-digit BCD arithmetic"},
    {"source": "Bcdadd4.txt", "focus": "multi-digit BCD arithmetic"},
    {"source": "Popcount3.txt", "focus": "small population count"},
    {"source": "Popcount255.txt", "focus": "wide population count"},
    {"source": "barrel_shifter_8bit.txt", "focus": "logical shifting stages"},
    {"source": "Rotate_8.txt", "focus": "bidirectional rotation"},
    {"source": "Rotate_16.txt", "focus": "wide rotation network"},
    {"source": "dual_address_rom.txt", "focus": "multi-port ROM access"},
    {"source": "dual_address_ram.txt", "focus": "dual-address RAM access"},
    {"source": "Dff.txt", "focus": "single-bit register"},
    {"source": "Dff8.txt", "focus": "wide register"},
    {"source": "Dff8r.txt", "focus": "register with reset"},
    {"source": "Dff16e.txt", "focus": "byte-enable register"},
    {"source": "muxdff.txt", "focus": "register with load-select path"},
    {"source": "Count10.txt", "focus": "modulo counter"},
    {"source": "Count15.txt", "focus": "binary wraparound counter"},
    {"source": "Count1to10.txt", "focus": "non-zero-start counter"},
    {"source": "Countbcd.txt", "focus": "cascaded BCD counter"},
    {"source": "bcd_counter.txt", "focus": "edge-triggered BCD counting"},
    {"source": "alt_bcd_counter.txt", "focus": "clock-divided BCD counting"},
    {"source": "timer.txt", "focus": "countdown timer"},
    {"source": "period_counter.txt", "focus": "measurement FSM"},
    {"source": "universal_binary_counter.txt", "focus": "parameterized control counter"},
    {"source": "shift_reg.sv.txt", "focus": "parameterized shift register"},
    {"source": "Universal_shift_reg.txt", "focus": "universal shift-register control"},
    {"source": "lfsr.txt", "focus": "basic LFSR"},
    {"source": "Lfsr5.txt", "focus": "custom feedback LFSR"},
    {"source": "edgecapture.txt", "focus": "sticky falling-edge capture"},
    {"source": "Edgedetect.txt", "focus": "vector rising-edge detection"},
    {"source": "dual_edge_detector_simpler.txt", "focus": "dual-edge detection"},
    {"source": "moore.txt", "focus": "simple FSM output pattern"},
    {"source": "traffic_light.txt", "focus": "controller FSM"},
    {"source": "Fsm serial.txt", "focus": "FSM with explicit counter"},
]


DESCRIPTION_APPEND_NOTES = {
    "dual_address_rom.txt": (
        "PyRTL refinement: `wr_en` is treated as a read qualifier for port 0, not as a real ROM write signal. "
        "Disabled outputs drive zero because PyRTL does not model high-impedance outputs in this style."
    ),
    "dual_address_ram.txt": (
        "PyRTL refinement: the translation uses one `MemBlock` write port and two asynchronous read ports. "
        "Disabled outputs drive zero instead of high impedance."
    ),
    "bcd_counter.txt": (
        "PyRTL refinement: the external debounce helper is not recreated here, so the switch input is assumed to "
        "arrive already debounced and the design increments on a detected rising edge of `sw_hi = ~sw`."
    ),
    "Count1to10.txt": (
        "PyRTL refinement: the prose mentions asynchronous reset, but the provided implementation behaves "
        "synchronously. The PyRTL version follows the implementation and uses register initialization plus "
        "clocked reset handling."
    ),
    "shift_reg.sv.txt": (
        "PyRTL refinement: the generic `Depth` parameter is represented as the Python argument `depth`, and the "
        "active-low reset input clears every stage to zero."
    ),
    "universal_binary_counter.txt": (
        "PyRTL refinement: the counter width is inferred from the bitwidth of `d`, which keeps the function "
        "portable across different widths."
    ),
    "traffic_light.txt": (
        "PyRTL refinement: there is no explicit reset input in the original source, so the controller starts in "
        "state 0 using the register `reset_value`."
    ),
    "edgecapture.txt": (
        "PyRTL refinement: the previous-sample register continues tracking the input during reset handling so that "
        "post-reset falling-edge capture matches the intended behavior."
    ),
}


CODE_BY_SOURCE = {
    "Reduction.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            parity = pyrtl.WireVector(bitwidth=1, name='parity')
            parity <<= in_[0] ^ in_[1] ^ in_[2] ^ in_[3] ^ in_[4] ^ in_[5] ^ in_[6] ^ in_[7]
            return parity
        """
    ),
    "7Vector1.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            out_hi = pyrtl.WireVector(bitwidth=8, name='out_hi')
            out_lo = pyrtl.WireVector(bitwidth=8, name='out_lo')
            out_hi <<= in_[8:16]
            out_lo <<= in_[0:8]
            return out_hi, out_lo
        """
    ),
    "Vectorgates.txt": code(
        """
        import pyrtl

        def TopModule(a, b):
            zero3 = pyrtl.Const(0, bitwidth=3)
            out_or_bitwise = pyrtl.WireVector(bitwidth=3, name='out_or_bitwise')
            out_or_logical = pyrtl.WireVector(bitwidth=1, name='out_or_logical')
            out_not = pyrtl.WireVector(bitwidth=6, name='out_not')

            out_or_bitwise <<= a | b
            out_or_logical <<= (a != zero3) | (b != zero3)
            out_not <<= pyrtl.concat(~b, ~a)
            return out_or_bitwise, out_or_logical, out_not
        """
    ),
    "Gates4.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            out_and = pyrtl.WireVector(bitwidth=1, name='out_and')
            out_or = pyrtl.WireVector(bitwidth=1, name='out_or')
            out_xor = pyrtl.WireVector(bitwidth=1, name='out_xor')

            out_and <<= in_[0] & in_[1] & in_[2] & in_[3]
            out_or <<= in_[0] | in_[1] | in_[2] | in_[3]
            out_xor <<= in_[0] ^ in_[1] ^ in_[2] ^ in_[3]
            return out_and, out_or, out_xor
        """
    ),
    "Mux2to1.txt": code(
        """
        import pyrtl

        def TopModule(a, b, sel):
            out = pyrtl.WireVector(bitwidth=1, name='out')
            out <<= pyrtl.select(sel, truecase=b, falsecase=a)
            return out
        """
    ),
    "Mux_8_to_1.txt": code(
        """
        import pyrtl

        def TopModule(S, in0, in1, in2, in3, in4, in5, in6, in7):
            selected = in0
            selected = pyrtl.select(S == pyrtl.Const(1, bitwidth=3), truecase=in1, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(2, bitwidth=3), truecase=in2, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(3, bitwidth=3), truecase=in3, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(4, bitwidth=3), truecase=in4, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(5, bitwidth=3), truecase=in5, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(6, bitwidth=3), truecase=in6, falsecase=selected)
            selected = pyrtl.select(S == pyrtl.Const(7, bitwidth=3), truecase=in7, falsecase=selected)

            Mux_Out = pyrtl.WireVector(bitwidth=1, name='Mux_Out')
            Mux_Out <<= selected
            return Mux_Out
        """
    ),
    "Mux256to1.txt": code(
        """
        import pyrtl

        def TopModule(in_, sel):  # in_ corresponds to the original Verilog signal named "in"
            selected = pyrtl.Const(0, bitwidth=1)
            for idx in range(256):
                selected = pyrtl.select(
                    sel == pyrtl.Const(idx, bitwidth=8),
                    truecase=in_[idx],
                    falsecase=selected,
                )

            out = pyrtl.WireVector(bitwidth=1, name='out')
            out <<= selected
            return out
        """
    ),
    "binary_decoder_2x4.txt": code(
        """
        import pyrtl

        def TopModule(en, a):
            terms = [en & (a == pyrtl.Const(idx, bitwidth=2)) for idx in range(4)]
            bcode = pyrtl.WireVector(bitwidth=4, name='bcode')
            bcode <<= pyrtl.concat(terms[3], terms[2], terms[1], terms[0])
            return bcode
        """
    ),
    "binary_decoder_3x8.txt": code(
        """
        import pyrtl

        def TopModule(a):
            terms = [a == pyrtl.Const(idx, bitwidth=3) for idx in range(8)]
            bcode = pyrtl.WireVector(bitwidth=8, name='bcode')
            bcode <<= pyrtl.concat(*reversed(terms))
            return bcode
        """
    ),
    "binary_decoder_4x16.txt": code(
        """
        import pyrtl

        def TopModule(a):
            terms = [a == pyrtl.Const(idx, bitwidth=4) for idx in range(16)]
            bcode = pyrtl.WireVector(bitwidth=16, name='bcode')
            bcode <<= pyrtl.concat(*reversed(terms))
            return bcode
        """
    ),
    "dual_prioenc.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            first_expr = pyrtl.Const(0, bitwidth=4)
            second_expr = pyrtl.Const(0, bitwidth=4)
            found_first = pyrtl.Const(0, bitwidth=1)
            found_second = pyrtl.Const(0, bitwidth=1)

            for idx in range(11, -1, -1):
                bit = in_[idx]
                pos = pyrtl.Const(idx + 1, bitwidth=4)
                assign_first = bit & ~found_first
                assign_second = bit & found_first & ~found_second
                first_expr = pyrtl.select(assign_first, truecase=pos, falsecase=first_expr)
                second_expr = pyrtl.select(assign_second, truecase=pos, falsecase=second_expr)
                found_first = found_first | bit
                found_second = found_second | assign_second

            first = pyrtl.WireVector(bitwidth=4, name='first')
            second = pyrtl.WireVector(bitwidth=4, name='second')
            first <<= first_expr
            second <<= second_expr
            return first, second
        """
    ),
    "dual_comparator.txt": code(
        """
        import pyrtl

        def TopModule(a, b, mode):
            sign_a = a[7]
            sign_b = b[7]
            signed_gt = ((~sign_a) & sign_b) | ((sign_a == sign_b) & (a > b))
            unsigned_gt = a > b

            agtb = pyrtl.WireVector(bitwidth=1, name='agtb')
            agtb <<= pyrtl.select(mode, truecase=signed_gt, falsecase=unsigned_gt)
            return agtb
        """
    ),
    "greater_than_4bit.txt": code(
        """
        import pyrtl

        def TopModule(a, b):
            gt = pyrtl.WireVector(bitwidth=1, name='gt')
            gt <<= a > b
            return gt
        """
    ),
    "adder.txt": code(
        """
        import pyrtl

        def TopModule(a, b):
            total = pyrtl.concat(pyrtl.Const(0, bitwidth=1), a) + pyrtl.concat(pyrtl.Const(0, bitwidth=1), b)
            c = pyrtl.WireVector(bitwidth=1, name='c')
            s = pyrtl.WireVector(bitwidth=8, name='s')
            c <<= total[8]
            s <<= total[0:8]
            return c, s
        """
    ),
    "adder32.txt": code(
        """
        import pyrtl

        def TopModule(A, B, Ci):
            total = (
                pyrtl.concat(pyrtl.Const(0, bitwidth=1), A)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=1), B)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=32), Ci)
            )
            S = pyrtl.WireVector(bitwidth=32, name='S')
            Co = pyrtl.WireVector(bitwidth=1, name='Co')
            S <<= total[0:32]
            Co <<= total[32]
            return S, Co
        """
    ),
    "carry_save_adder.txt": code(
        """
        import pyrtl

        def TopModule(a, b, c, d):
            total = (
                pyrtl.concat(pyrtl.Const(0, bitwidth=2), a)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=2), b)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=2), c)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=2), d)
            )
            sum_ = pyrtl.WireVector(bitwidth=5, name='sum')
            cout = pyrtl.WireVector(bitwidth=1, name='cout')
            sum_ <<= total[0:5]
            cout <<= total[5]
            return sum_, cout
        """
    ),
    "carry_look_ahead_adder.txt": code(
        """
        import pyrtl

        def TopModule(a, b, cin):
            total = (
                pyrtl.concat(pyrtl.Const(0, bitwidth=1), a)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=1), b)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=16), cin)
            )
            sum_ = pyrtl.WireVector(bitwidth=16, name='sum')
            cout = pyrtl.WireVector(bitwidth=1, name='cout')
            sum_ <<= total[0:16]
            cout <<= total[16]
            return sum_, cout
        """
    ),
    "bcd_adder.txt": code(
        """
        import pyrtl

        def TopModule(a, b, cin):
            temp = (
                pyrtl.concat(pyrtl.Const(0, bitwidth=1), a)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=1), b)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=4), cin)
            )
            needs_correction = temp > pyrtl.Const(9, bitwidth=5)
            corrected = (temp + pyrtl.Const(6, bitwidth=5))[0:5]

            sum_ = pyrtl.WireVector(bitwidth=4, name='sum')
            cout = pyrtl.WireVector(bitwidth=1, name='cout')
            sum_ <<= pyrtl.select(needs_correction, truecase=corrected[0:4], falsecase=temp[0:4])
            cout <<= pyrtl.select(
                needs_correction,
                truecase=pyrtl.Const(1, bitwidth=1),
                falsecase=pyrtl.Const(0, bitwidth=1),
            )
            return sum_, cout
        """
    ),
    "Bcdadd4.txt": code(
        """
        import pyrtl

        def _bcd_digit_add(a_digit, b_digit, carry_in):
            temp = (
                pyrtl.concat(pyrtl.Const(0, bitwidth=1), a_digit)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=1), b_digit)
                + pyrtl.concat(pyrtl.Const(0, bitwidth=4), carry_in)
            )
            needs_correction = temp > pyrtl.Const(9, bitwidth=5)
            corrected = (temp + pyrtl.Const(6, bitwidth=5))[0:5]
            digit_sum = pyrtl.select(needs_correction, truecase=corrected[0:4], falsecase=temp[0:4])
            digit_cout = pyrtl.select(
                needs_correction,
                truecase=pyrtl.Const(1, bitwidth=1),
                falsecase=pyrtl.Const(0, bitwidth=1),
            )
            return digit_sum, digit_cout

        def TopModule(a, b, cin):
            s0, c0 = _bcd_digit_add(a[0:4], b[0:4], cin)
            s1, c1 = _bcd_digit_add(a[4:8], b[4:8], c0)
            s2, c2 = _bcd_digit_add(a[8:12], b[8:12], c1)
            s3, cout = _bcd_digit_add(a[12:16], b[12:16], c2)

            sum_ = pyrtl.WireVector(bitwidth=16, name='sum')
            sum_ <<= pyrtl.concat(s3, s2, s1, s0)
            return cout, sum_
        """
    ),
    "Popcount3.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            count = pyrtl.Const(0, bitwidth=2)
            for idx in range(3):
                addend = pyrtl.concat(pyrtl.Const(0, bitwidth=1), in_[idx])
                count = (count + addend)[0:2]

            out = pyrtl.WireVector(bitwidth=2, name='out')
            out <<= count
            return out
        """
    ),
    "Popcount255.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            count = pyrtl.Const(0, bitwidth=8)
            for idx in range(255):
                addend = pyrtl.concat(pyrtl.Const(0, bitwidth=7), in_[idx])
                count = (count + addend)[0:8]

            out = pyrtl.WireVector(bitwidth=8, name='out')
            out <<= count
            return out
        """
    ),
    "barrel_shifter_8bit.txt": code(
        """
        import pyrtl

        def TopModule(in_, ctrl):  # in_ corresponds to the original Verilog signal named "in"
            stage4 = pyrtl.select(
                ctrl[2],
                truecase=pyrtl.concat(pyrtl.Const(0, bitwidth=4), in_[4:8]),
                falsecase=in_,
            )
            stage2 = pyrtl.select(
                ctrl[1],
                truecase=pyrtl.concat(pyrtl.Const(0, bitwidth=2), stage4[2:8]),
                falsecase=stage4,
            )
            stage1 = pyrtl.select(
                ctrl[0],
                truecase=pyrtl.concat(pyrtl.Const(0, bitwidth=1), stage2[1:8]),
                falsecase=stage2,
            )

            out = pyrtl.WireVector(bitwidth=8, name='out')
            out <<= stage1
            return out
        """
    ),
    "Rotate_8.txt": code(
        """
        import pyrtl

        def TopModule(num, amt, LR):
            right1 = pyrtl.select(amt[0], truecase=pyrtl.concat(num[0:1], num[1:8]), falsecase=num)
            right2 = pyrtl.select(amt[1], truecase=pyrtl.concat(right1[0:2], right1[2:8]), falsecase=right1)
            right4 = pyrtl.select(amt[2], truecase=pyrtl.concat(right2[0:4], right2[4:8]), falsecase=right2)

            left1 = pyrtl.select(amt[0], truecase=pyrtl.concat(num[0:7], num[7:8]), falsecase=num)
            left2 = pyrtl.select(amt[1], truecase=pyrtl.concat(left1[0:6], left1[6:8]), falsecase=left1)
            left4 = pyrtl.select(amt[2], truecase=pyrtl.concat(left2[0:4], left2[4:8]), falsecase=left2)

            real_out = pyrtl.WireVector(bitwidth=8, name='real_out')
            real_out <<= pyrtl.select(LR, truecase=left4, falsecase=right4)
            return real_out
        """
    ),
    "Rotate_16.txt": code(
        """
        import pyrtl

        def TopModule(num, amt, LR):
            right1 = pyrtl.select(amt[0], truecase=pyrtl.concat(num[0:1], num[1:16]), falsecase=num)
            right2 = pyrtl.select(amt[1], truecase=pyrtl.concat(right1[0:2], right1[2:16]), falsecase=right1)
            right4 = pyrtl.select(amt[2], truecase=pyrtl.concat(right2[0:4], right2[4:16]), falsecase=right2)
            right8 = pyrtl.select(amt[3], truecase=pyrtl.concat(right4[0:8], right4[8:16]), falsecase=right4)

            left1 = pyrtl.select(amt[0], truecase=pyrtl.concat(num[0:15], num[15:16]), falsecase=num)
            left2 = pyrtl.select(amt[1], truecase=pyrtl.concat(left1[0:14], left1[14:16]), falsecase=left1)
            left4 = pyrtl.select(amt[2], truecase=pyrtl.concat(left2[0:12], left2[12:16]), falsecase=left2)
            left8 = pyrtl.select(amt[3], truecase=pyrtl.concat(left4[0:8], left4[8:16]), falsecase=left4)

            real_out = pyrtl.WireVector(bitwidth=16, name='real_out')
            real_out <<= pyrtl.select(LR, truecase=left8, falsecase=right8)
            return real_out
        """
    ),
    "dual_address_rom.txt": code(
        """
        import pyrtl

        def TopModule(clk, wr_en, addr_in_0, addr_in_1, port_en_0, port_en_1):
            romdata = [
                0x24, 0x23, 0xE2, 0x21,
                0x45, 0xAE, 0xCB, 0x00,
                0xA3, 0x2A, 0xEC, 0x22,
                0x40, 0xA0, 0x0C, 0x00,
            ]
            rom = pyrtl.RomBlock(
                bitwidth=8,
                addrwidth=4,
                romdata=romdata,
                name='rom',
                max_read_ports=2,
                asynchronous=True,
            )

            data_out_0 = pyrtl.WireVector(bitwidth=8, name='data_out_0')
            data_out_1 = pyrtl.WireVector(bitwidth=8, name='data_out_1')
            data_out_0 <<= pyrtl.select(port_en_0 & wr_en, truecase=rom[addr_in_0], falsecase=pyrtl.Const(0, bitwidth=8))
            data_out_1 <<= pyrtl.select(port_en_1, truecase=rom[addr_in_1], falsecase=pyrtl.Const(0, bitwidth=8))
            return data_out_0, data_out_1
        """
    ),
    "dual_address_ram.txt": code(
        """
        import pyrtl

        def TopModule(clk, wr_en, data_in, addr_in_0, addr_in_1, port_en_0, port_en_1):
            ram = pyrtl.MemBlock(
                bitwidth=8,
                addrwidth=4,
                name='ram',
                max_read_ports=2,
                max_write_ports=1,
                asynchronous=True,
            )

            ram[addr_in_0] <<= pyrtl.MemBlock.EnabledWrite(data_in, port_en_0 & wr_en)

            data_out_0 = pyrtl.WireVector(bitwidth=8, name='data_out_0')
            data_out_1 = pyrtl.WireVector(bitwidth=8, name='data_out_1')
            data_out_0 <<= pyrtl.select(port_en_0, truecase=ram[addr_in_0], falsecase=pyrtl.Const(0, bitwidth=8))
            data_out_1 <<= pyrtl.select(port_en_1, truecase=ram[addr_in_1], falsecase=pyrtl.Const(0, bitwidth=8))
            return data_out_0, data_out_1
        """
    ),
    "Dff.txt": code(
        """
        import pyrtl

        def TopModule(d):
            q = pyrtl.Register(bitwidth=1, name='q', reset_value=0)
            q.next <<= d
            return q
        """
    ),
    "Dff8.txt": code(
        """
        import pyrtl

        def TopModule(d):
            q = pyrtl.Register(bitwidth=8, name='q', reset_value=0)
            q.next <<= d
            return q
        """
    ),
    "Dff8r.txt": code(
        """
        import pyrtl

        def TopModule(reset, d):
            q = pyrtl.Register(bitwidth=8, name='q', reset_value=0)
            q.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=8), falsecase=d)
            return q
        """
    ),
    "Dff16e.txt": code(
        """
        import pyrtl

        def TopModule(resetn, byteena, d):
            q = pyrtl.Register(bitwidth=16, name='q', reset_value=0)
            upper_next = pyrtl.select(byteena[1], truecase=d[8:16], falsecase=q[8:16])
            lower_next = pyrtl.select(byteena[0], truecase=d[0:8], falsecase=q[0:8])
            merged_next = pyrtl.concat(upper_next, lower_next)
            q.next <<= pyrtl.select(~resetn, truecase=pyrtl.Const(0, bitwidth=16), falsecase=merged_next)
            return q
        """
    ),
    "muxdff.txt": code(
        """
        import pyrtl

        def TopModule(L, rin, qin):
            Q = pyrtl.Register(bitwidth=1, name='Q', reset_value=0)
            Q.next <<= pyrtl.select(L, truecase=rin, falsecase=qin)
            return Q
        """
    ),
    "Count10.txt": code(
        """
        import pyrtl

        def TopModule(reset):
            q = pyrtl.Register(bitwidth=4, name='q', reset_value=0)
            incremented = (q + pyrtl.Const(1, bitwidth=4))[0:4]
            wrapped = pyrtl.select(q == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=incremented)
            q.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=wrapped)
            return q
        """
    ),
    "Count15.txt": code(
        """
        import pyrtl

        def TopModule(reset):
            q = pyrtl.Register(bitwidth=4, name='q', reset_value=0)
            incremented = (q + pyrtl.Const(1, bitwidth=4))[0:4]
            wrapped = pyrtl.select(q == pyrtl.Const(15, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=incremented)
            q.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=wrapped)
            return q
        """
    ),
    "Count1to10.txt": code(
        """
        import pyrtl

        def TopModule(reset):
            q = pyrtl.Register(bitwidth=4, name='q', reset_value=1)
            incremented = (q + pyrtl.Const(1, bitwidth=4))[0:4]
            wrapped = pyrtl.select(q == pyrtl.Const(10, bitwidth=4), truecase=pyrtl.Const(1, bitwidth=4), falsecase=incremented)
            q.next <<= pyrtl.select(reset, truecase=pyrtl.Const(1, bitwidth=4), falsecase=wrapped)
            return q
        """
    ),
    "Countbcd.txt": code(
        """
        import pyrtl

        def TopModule(reset):
            d0 = pyrtl.Register(bitwidth=4, name='digit0', reset_value=0)
            d1 = pyrtl.Register(bitwidth=4, name='digit1', reset_value=0)
            d2 = pyrtl.Register(bitwidth=4, name='digit2', reset_value=0)
            d3 = pyrtl.Register(bitwidth=4, name='digit3', reset_value=0)

            ena1 = d0 == pyrtl.Const(9, bitwidth=4)
            ena2 = ena1 & (d1 == pyrtl.Const(9, bitwidth=4))
            ena3 = ena2 & (d2 == pyrtl.Const(9, bitwidth=4))

            inc0 = (d0 + pyrtl.Const(1, bitwidth=4))[0:4]
            inc1 = (d1 + pyrtl.Const(1, bitwidth=4))[0:4]
            inc2 = (d2 + pyrtl.Const(1, bitwidth=4))[0:4]
            inc3 = (d3 + pyrtl.Const(1, bitwidth=4))[0:4]

            d0_next = pyrtl.select(d0 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=inc0)
            d1_advanced = pyrtl.select(d1 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=inc1)
            d2_advanced = pyrtl.select(d2 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=inc2)
            d3_advanced = pyrtl.select(d3 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=inc3)

            d0.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=d0_next)
            d1.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=pyrtl.select(ena1, truecase=d1_advanced, falsecase=d1))
            d2.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=pyrtl.select(ena2, truecase=d2_advanced, falsecase=d2))
            d3.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=pyrtl.select(ena3, truecase=d3_advanced, falsecase=d3))

            ena = pyrtl.WireVector(bitwidth=3, name='ena')
            q = pyrtl.WireVector(bitwidth=16, name='q')
            ena <<= pyrtl.concat(ena3, ena2, ena1)
            q <<= pyrtl.concat(d3, d2, d1, d0)
            return ena, q
        """
    ),
    "bcd_counter.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, sw):
            idle = pyrtl.Const(0, bitwidth=1)
            done = pyrtl.Const(1, bitwidth=1)

            state_reg = pyrtl.Register(bitwidth=1, name='state_reg', reset_value=0)
            dig1 = pyrtl.Register(bitwidth=4, name='dig1', reset_value=0)
            dig0 = pyrtl.Register(bitwidth=4, name='dig0', reset_value=0)
            sw_prev = pyrtl.Register(bitwidth=1, name='sw_prev', reset_value=0)

            sw_hi = ~sw
            r_edg = sw_hi & ~sw_prev

            dig0_inc = (dig0 + pyrtl.Const(1, bitwidth=4))[0:4]
            dig1_inc = (dig1 + pyrtl.Const(1, bitwidth=4))[0:4]
            next_dig0 = pyrtl.select(dig0 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=dig0_inc)
            next_dig1 = pyrtl.select(
                dig0 == pyrtl.Const(9, bitwidth=4),
                truecase=pyrtl.select(dig1 == pyrtl.Const(4, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=dig1_inc),
                falsecase=dig1,
            )

            state_reg.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=1),
                falsecase=pyrtl.select(state_reg == idle, truecase=pyrtl.select(r_edg, truecase=done, falsecase=idle), falsecase=idle),
            )
            dig0.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=4),
                falsecase=pyrtl.select((state_reg == idle) & r_edg, truecase=next_dig0, falsecase=dig0),
            )
            dig1.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=4),
                falsecase=pyrtl.select((state_reg == idle) & r_edg, truecase=next_dig1, falsecase=dig1),
            )
            sw_prev.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=1), falsecase=sw_hi)

            done_tick = pyrtl.WireVector(bitwidth=1, name='done_tick')
            done_tick <<= state_reg == done
            return dig1, dig0, done_tick
        """
    ),
    "alt_bcd_counter.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, go):
            s1 = pyrtl.Register(bitwidth=4, name='s1', reset_value=0)
            s0 = pyrtl.Register(bitwidth=4, name='s0', reset_value=0)
            ms0 = pyrtl.Register(bitwidth=4, name='ms0', reset_value=0)
            counter_reg = pyrtl.Register(bitwidth=23, name='counter_reg', reset_value=0)

            terminal = counter_reg == pyrtl.Const(4_999_999, bitwidth=23)
            counter_plus = (counter_reg + pyrtl.Const(1, bitwidth=23))[0:23]
            ms0_plus = (ms0 + pyrtl.Const(1, bitwidth=4))[0:4]
            s0_plus = (s0 + pyrtl.Const(1, bitwidth=4))[0:4]
            s1_plus = (s1 + pyrtl.Const(1, bitwidth=4))[0:4]

            ms0_wrap = pyrtl.select(ms0 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=ms0_plus)
            s0_wrap = pyrtl.select(s0 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=s0_plus)
            s1_wrap = pyrtl.select(s1 == pyrtl.Const(9, bitwidth=4), truecase=pyrtl.Const(0, bitwidth=4), falsecase=s1_plus)

            counter_reg.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=23),
                falsecase=pyrtl.select(go, truecase=pyrtl.select(terminal, truecase=pyrtl.Const(0, bitwidth=23), falsecase=counter_plus), falsecase=counter_reg),
            )
            ms0.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=4),
                falsecase=pyrtl.select(go & terminal, truecase=ms0_wrap, falsecase=ms0),
            )
            s0.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=4),
                falsecase=pyrtl.select(go & terminal & (ms0 == pyrtl.Const(9, bitwidth=4)), truecase=s0_wrap, falsecase=s0),
            )
            s1.next <<= pyrtl.select(
                ~rst_n,
                truecase=pyrtl.Const(0, bitwidth=4),
                falsecase=pyrtl.select(
                    go & terminal & (ms0 == pyrtl.Const(9, bitwidth=4)) & (s0 == pyrtl.Const(9, bitwidth=4)),
                    truecase=s1_wrap,
                    falsecase=s1,
                ),
            )
            return s1, s0, ms0
        """
    ),
    "timer.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, timer_start, timer_tick):
            timer_q = pyrtl.Register(bitwidth=7, name='timer_q', reset_value=0)
            decremented = (timer_q - pyrtl.Const(1, bitwidth=7))[0:7]
            tick_value = pyrtl.select(timer_q == pyrtl.Const(0, bitwidth=7), truecase=pyrtl.Const(0, bitwidth=7), falsecase=decremented)
            next_value = pyrtl.select(
                timer_start,
                truecase=pyrtl.Const(0x7F, bitwidth=7),
                falsecase=pyrtl.select(timer_tick, truecase=tick_value, falsecase=timer_q),
            )
            timer_q.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=7), falsecase=next_value)

            timer_up = pyrtl.WireVector(bitwidth=1, name='timer_up')
            timer_up <<= timer_q == pyrtl.Const(0, bitwidth=7)
            return timer_up
        """
    ),
    "period_counter.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, start, signal):
            idle = pyrtl.Const(0, bitwidth=2)
            waiting = pyrtl.Const(1, bitwidth=2)
            op = pyrtl.Const(2, bitwidth=2)
            done = pyrtl.Const(3, bitwidth=2)
            n_minus_1 = pyrtl.Const(49, bitwidth=6)

            state_reg = pyrtl.Register(bitwidth=2, name='state_reg', reset_value=0)
            period_reg = pyrtl.Register(bitwidth=20, name='period_reg', reset_value=0)
            tick_reg = pyrtl.Register(bitwidth=6, name='tick_reg', reset_value=0)
            signal_reg = pyrtl.Register(bitwidth=1, name='signal_reg', reset_value=0)

            edg = signal & ~signal_reg
            next_state = state_reg
            next_state = pyrtl.select(state_reg == idle, truecase=pyrtl.select(start, truecase=waiting, falsecase=idle), falsecase=next_state)
            next_state = pyrtl.select(state_reg == waiting, truecase=pyrtl.select(edg, truecase=op, falsecase=waiting), falsecase=next_state)
            next_state = pyrtl.select(state_reg == op, truecase=pyrtl.select(edg, truecase=done, falsecase=op), falsecase=next_state)
            next_state = pyrtl.select(state_reg == done, truecase=idle, falsecase=next_state)

            tick_plus = (tick_reg + pyrtl.Const(1, bitwidth=6))[0:6]
            period_plus = (period_reg + pyrtl.Const(1, bitwidth=20))[0:20]

            next_tick = tick_reg
            next_tick = pyrtl.select((state_reg == idle) & start, truecase=pyrtl.Const(0, bitwidth=6), falsecase=next_tick)
            next_tick = pyrtl.select(
                (state_reg == op) & ~edg,
                truecase=pyrtl.select(tick_reg == n_minus_1, truecase=pyrtl.Const(0, bitwidth=6), falsecase=tick_plus),
                falsecase=next_tick,
            )

            next_period = period_reg
            next_period = pyrtl.select((state_reg == idle) & start, truecase=pyrtl.Const(0, bitwidth=20), falsecase=next_period)
            next_period = pyrtl.select(
                (state_reg == op) & ~edg & (tick_reg == n_minus_1),
                truecase=period_plus,
                falsecase=next_period,
            )

            state_reg.next <<= pyrtl.select(~rst_n, truecase=idle, falsecase=next_state)
            tick_reg.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=6), falsecase=next_tick)
            period_reg.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=20), falsecase=next_period)
            signal_reg.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=1), falsecase=signal)

            ready = pyrtl.WireVector(bitwidth=1, name='ready')
            done_tick = pyrtl.WireVector(bitwidth=1, name='done_tick')
            period = pyrtl.WireVector(bitwidth=20, name='period')
            ready <<= state_reg == idle
            done_tick <<= state_reg == done
            period <<= period_reg
            return ready, done_tick, period
        """
    ),
    "universal_binary_counter.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, syn_clr, load, en, up, d):
            width = len(d)
            q = pyrtl.Register(bitwidth=width, name='q', reset_value=0)
            all_ones = pyrtl.Const((1 << width) - 1, bitwidth=width)

            q_plus = (q + pyrtl.Const(1, bitwidth=width))[0:width]
            q_minus = (q - pyrtl.Const(1, bitwidth=width))[0:width]

            next_q = pyrtl.select(
                syn_clr,
                truecase=pyrtl.Const(0, bitwidth=width),
                falsecase=pyrtl.select(
                    load,
                    truecase=d,
                    falsecase=pyrtl.select(en & up, truecase=q_plus, falsecase=pyrtl.select(en & ~up, truecase=q_minus, falsecase=q)),
                ),
            )
            q.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=width), falsecase=next_q)

            max_tick = pyrtl.WireVector(bitwidth=1, name='max_tick')
            min_tick = pyrtl.WireVector(bitwidth=1, name='min_tick')
            max_tick <<= q == all_ones
            min_tick <<= q == pyrtl.Const(0, bitwidth=width)
            return q, max_tick, min_tick
        """
    ),
    "shift_reg.sv.txt": code(
        """
        import pyrtl

        def TopModule(rst_ni, d_i, depth=1):
            bitwidth = len(d_i)
            if depth <= 0:
                d_o = pyrtl.WireVector(bitwidth=bitwidth, name='d_o')
                d_o <<= d_i
                return d_o

            stages = [
                pyrtl.Register(bitwidth=bitwidth, name=f'stage_{idx}', reset_value=0)
                for idx in range(depth)
            ]

            for idx, stage in enumerate(stages):
                source = d_i if idx == 0 else stages[idx - 1]
                stage.next <<= pyrtl.select(rst_ni, truecase=source, falsecase=pyrtl.Const(0, bitwidth=bitwidth))

            d_o = pyrtl.WireVector(bitwidth=bitwidth, name='d_o')
            d_o <<= stages[-1]
            return d_o
        """
    ),
    "Universal_shift_reg.txt": code(
        """
        import pyrtl

        def _mux8_expr(sel, options):
            result = options[0]
            for idx in range(1, 8):
                result = pyrtl.select(sel == pyrtl.Const(idx, bitwidth=3), truecase=options[idx], falsecase=result)
            return result

        def TopModule(clear, S, I):
            O = pyrtl.Register(bitwidth=4, name='O', reset_value=0)

            d0 = _mux8_expr(S, [O[0], pyrtl.Const(0, bitwidth=1), O[1], I[0], ~O[0], O[3], O[1], O[2]])
            d1 = _mux8_expr(S, [O[1], O[0], O[2], I[1], ~O[1], O[0], O[2], O[3]])
            d2 = _mux8_expr(S, [O[2], O[1], O[3], I[2], ~O[2], O[1], O[3], O[0]])
            d3 = _mux8_expr(S, [O[3], O[2], pyrtl.Const(0, bitwidth=1), I[3], ~O[3], O[2], O[0], O[1]])

            next_state = pyrtl.concat(d3, d2, d1, d0)
            O.next <<= pyrtl.select(clear, truecase=pyrtl.Const(0, bitwidth=4), falsecase=next_state)
            return O
        """
    ),
    "lfsr.txt": code(
        """
        import pyrtl

        def TopModule(rst):
            out = pyrtl.Register(bitwidth=4, name='out', reset_value=0)
            feedback = ~(out[3] ^ out[2])
            shifted = pyrtl.concat(out[0:3], feedback)
            out.next <<= pyrtl.select(rst, truecase=pyrtl.Const(0, bitwidth=4), falsecase=shifted)
            return out
        """
    ),
    "Lfsr5.txt": code(
        """
        import pyrtl

        def TopModule(reset):
            q = pyrtl.Register(bitwidth=5, name='q', reset_value=1)
            next_q = pyrtl.concat(q[0], q[4], q[3] ^ q[0], q[2], q[1])
            q.next <<= pyrtl.select(reset, truecase=pyrtl.Const(1, bitwidth=5), falsecase=next_q)
            return q
        """
    ),
    "edgecapture.txt": code(
        """
        import pyrtl

        def TopModule(reset, in_):  # in_ corresponds to the original Verilog signal named "in"
            d_last = pyrtl.Register(bitwidth=32, name='d_last', reset_value=0)
            out = pyrtl.Register(bitwidth=32, name='out', reset_value=0)

            d_last.next <<= in_
            out.next <<= pyrtl.select(
                reset,
                truecase=pyrtl.Const(0, bitwidth=32),
                falsecase=out | ((~in_) & d_last),
            )
            return out
        """
    ),
    "Edgedetect.txt": code(
        """
        import pyrtl

        def TopModule(in_):  # in_ corresponds to the original Verilog signal named "in"
            prev = pyrtl.Register(bitwidth=8, name='prev', reset_value=0)
            pedge = pyrtl.WireVector(bitwidth=8, name='pedge')
            pedge <<= in_ & ~prev
            prev.next <<= in_
            return pedge
        """
    ),
    "dual_edge_detector_simpler.txt": code(
        """
        import pyrtl

        def TopModule(rst_n, level):
            level_reg = pyrtl.Register(bitwidth=1, name='level_reg', reset_value=0)
            level_reg.next <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=1), falsecase=level)

            edg = pyrtl.WireVector(bitwidth=1, name='edg')
            edg <<= pyrtl.select(~rst_n, truecase=pyrtl.Const(0, bitwidth=1), falsecase=level ^ level_reg)
            return edg
        """
    ),
    "moore.txt": code(
        """
        import pyrtl

        def TopModule(reset, in_):  # in_ corresponds to the original Verilog signal named "in"
            zero = pyrtl.Const(0, bitwidth=2)
            one1 = pyrtl.Const(1, bitwidth=2)
            two1s = pyrtl.Const(2, bitwidth=2)

            state = pyrtl.Register(bitwidth=2, name='state', reset_value=0)
            next_state = state
            next_state = pyrtl.select(state == zero, truecase=pyrtl.select(in_, truecase=one1, falsecase=zero), falsecase=next_state)
            next_state = pyrtl.select(state == one1, truecase=pyrtl.select(in_, truecase=two1s, falsecase=zero), falsecase=next_state)
            next_state = pyrtl.select(state == two1s, truecase=pyrtl.select(in_, truecase=two1s, falsecase=zero), falsecase=next_state)
            state.next <<= pyrtl.select(reset, truecase=zero, falsecase=next_state)

            out = pyrtl.WireVector(bitwidth=1, name='out')
            out <<= state == two1s
            return out
        """
    ),
    "traffic_light.txt": code(
        """
        import pyrtl

        def TopModule(Sa, Sb):
            state = pyrtl.Register(bitwidth=4, name='state', reset_value=0)

            is0 = state == pyrtl.Const(0, bitwidth=4)
            is1 = state == pyrtl.Const(1, bitwidth=4)
            is2 = state == pyrtl.Const(2, bitwidth=4)
            is3 = state == pyrtl.Const(3, bitwidth=4)
            is4 = state == pyrtl.Const(4, bitwidth=4)
            is5 = state == pyrtl.Const(5, bitwidth=4)
            is6 = state == pyrtl.Const(6, bitwidth=4)
            is7 = state == pyrtl.Const(7, bitwidth=4)
            is8 = state == pyrtl.Const(8, bitwidth=4)
            is9 = state == pyrtl.Const(9, bitwidth=4)
            is10 = state == pyrtl.Const(10, bitwidth=4)
            is11 = state == pyrtl.Const(11, bitwidth=4)
            is12 = state == pyrtl.Const(12, bitwidth=4)

            next_state = state
            next_state = pyrtl.select(is0, truecase=pyrtl.Const(1, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is1, truecase=pyrtl.Const(2, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is2, truecase=pyrtl.Const(3, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is3, truecase=pyrtl.Const(4, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is4, truecase=pyrtl.Const(5, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is5, truecase=pyrtl.select(Sb, truecase=pyrtl.Const(6, bitwidth=4), falsecase=pyrtl.Const(5, bitwidth=4)), falsecase=next_state)
            next_state = pyrtl.select(is6, truecase=pyrtl.Const(7, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is7, truecase=pyrtl.Const(8, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is8, truecase=pyrtl.Const(9, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is9, truecase=pyrtl.Const(10, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is10, truecase=pyrtl.Const(11, bitwidth=4), falsecase=next_state)
            next_state = pyrtl.select(is11, truecase=pyrtl.select(Sa | ~Sb, truecase=pyrtl.Const(12, bitwidth=4), falsecase=pyrtl.Const(11, bitwidth=4)), falsecase=next_state)
            next_state = pyrtl.select(is12, truecase=pyrtl.Const(0, bitwidth=4), falsecase=next_state)
            state.next <<= next_state

            Ra = pyrtl.WireVector(bitwidth=1, name='Ra')
            Rb = pyrtl.WireVector(bitwidth=1, name='Rb')
            Ga = pyrtl.WireVector(bitwidth=1, name='Ga')
            Gb = pyrtl.WireVector(bitwidth=1, name='Gb')
            Ya = pyrtl.WireVector(bitwidth=1, name='Ya')
            Yb = pyrtl.WireVector(bitwidth=1, name='Yb')

            Ra <<= is7 | is8 | is9 | is10 | is11 | is12
            Rb <<= is0 | is1 | is2 | is3 | is4 | is5 | is6
            Ga <<= is0 | is1 | is2 | is3 | is4 | is5
            Gb <<= is7 | is8 | is9 | is10 | is11
            Ya <<= is6
            Yb <<= is12
            return Ra, Rb, Ga, Gb, Ya, Yb
        """
    ),
    "Fsm serial.txt": code(
        """
        import pyrtl

        def TopModule(reset, in_):  # in_ corresponds to the original Verilog signal named "in"
            rc = pyrtl.Const(0, bitwidth=2)
            dn = pyrtl.Const(1, bitwidth=2)
            rd = pyrtl.Const(2, bitwidth=2)
            err = pyrtl.Const(3, bitwidth=2)

            state = pyrtl.Register(bitwidth=2, name='state', reset_value=2)
            counter = pyrtl.Register(bitwidth=4, name='i', reset_value=0)

            next_state = state
            next_state = pyrtl.select(state == rd, truecase=pyrtl.select(in_, truecase=rd, falsecase=rc), falsecase=next_state)
            next_state = pyrtl.select(
                state == rc,
                truecase=pyrtl.select(
                    counter == pyrtl.Const(8, bitwidth=4),
                    truecase=pyrtl.select(in_, truecase=dn, falsecase=err),
                    falsecase=rc,
                ),
                falsecase=next_state,
            )
            next_state = pyrtl.select(state == dn, truecase=pyrtl.select(in_, truecase=rd, falsecase=rc), falsecase=next_state)
            next_state = pyrtl.select(state == err, truecase=pyrtl.select(in_, truecase=rd, falsecase=err), falsecase=next_state)

            counter_plus = (counter + pyrtl.Const(1, bitwidth=4))[0:4]
            next_counter = counter
            next_counter = pyrtl.select((state == rc) & (counter != pyrtl.Const(8, bitwidth=4)), truecase=counter_plus, falsecase=next_counter)
            next_counter = pyrtl.select((state == err) | (state == dn), truecase=pyrtl.Const(0, bitwidth=4), falsecase=next_counter)

            state.next <<= pyrtl.select(reset, truecase=rd, falsecase=next_state)
            counter.next <<= pyrtl.select(reset, truecase=pyrtl.Const(0, bitwidth=4), falsecase=next_counter)

            done = pyrtl.WireVector(bitwidth=1, name='done')
            done <<= state == dn
            return done
        """
    ),
}


def parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in SECTION_RE.finditer(text):
        sections[match.group("name").strip()] = match.group("body").strip()
    return sections


def refined_description(source_name: str, original: str) -> str:
    note = DESCRIPTION_APPEND_NOTES.get(source_name)
    if not note:
        return original.strip()
    return f"{original.strip()}\n\n{note}"


def verify_code(source_name: str, snippet: str) -> None:
    ast.parse(snippet, filename=source_name)
    if "def TopModule(" not in snippet:
        raise ValueError(f"{source_name} is missing TopModule")


def render_entry(source_name: str, source_text: str) -> str:
    sections = parse_sections(source_text)
    required = [
        "Keyword",
        "Design Category",
        "Design Function Description",
        "Input Signal Description",
        "Output Signal Description",
    ]
    missing = [key for key in required if key not in sections]
    if missing:
        raise ValueError(f"{source_name} is missing sections: {missing}")

    snippet = CODE_BY_SOURCE[source_name]
    verify_code(source_name, snippet)

    parts = [
        f"[Keyword]: {sections['Keyword'].strip()}",
        "",
        f"[Design Category]: {sections['Design Category'].strip()}",
        "",
        "[Design Function Description]:",
        refined_description(source_name, sections["Design Function Description"]),
        "",
        "[Input Signal Description]:",
        sections["Input Signal Description"].strip(),
        "",
        "[Output Signal Description]:",
        sections["Output Signal Description"].strip(),
        "",
        "[Design Detail]:",
        "```python",
        snippet.rstrip(),
        "```",
        "",
    ]
    return "\n".join(parts)


def write_readme() -> None:
    readme = textwrap.dedent(
        """
        # kb_pyrtl

        This folder contains 50 curated PyRTL-ready RAG entries converted from the original `knowledge_base` corpus.

        Selection criteria:
        - high signal-to-noise examples instead of metadata, logs, or malformed entries
        - broad coverage across combinational logic, arithmetic, memories, counters, shift registers, edge detectors, and FSMs
        - designs that are practical to express cleanly in PyRTL using `WireVector`, `Register`, `MemBlock`, and `RomBlock`

        Notes:
        - file names intentionally match the selected source entries so retrieval stays traceable
        - disabled RAM/ROM outputs are driven to zero in the PyRTL versions instead of high impedance
        - some sources with external helper modules were refined to compact self-contained PyRTL behavior
        - `error_correction/code_rag/index.py` still points at `knowledge_base`; update the watched directory if you want to index `kb_pyrtl`
        """
    ).strip() + "\n"
    (OUTPUT_DIR / "README.md").write_text(readme, encoding="utf-8")


def write_manifest() -> None:
    rows = [
        {
            "source_file": entry["source"],
            "target_file": entry["source"],
            "focus_area": entry["focus"],
        }
        for entry in SELECTED
    ]
    with (OUTPUT_DIR / "selection_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_file", "target_file", "focus_area"])
        writer.writeheader()
        writer.writerows(rows)


def build_kb() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for entry in SELECTED:
        source_name = entry["source"]
        source_path = SOURCE_DIR / source_name
        if not source_path.exists():
            raise FileNotFoundError(f"Missing source entry: {source_path}")

        source_text = source_path.read_text(encoding="utf-8", errors="ignore")
        rendered = render_entry(source_name, source_text)
        (OUTPUT_DIR / source_name).write_text(rendered, encoding="utf-8")

    write_readme()
    write_manifest()


if __name__ == "__main__":
    build_kb()
    print(f"Wrote {len(SELECTED)} PyRTL KB entries to {OUTPUT_DIR}")
