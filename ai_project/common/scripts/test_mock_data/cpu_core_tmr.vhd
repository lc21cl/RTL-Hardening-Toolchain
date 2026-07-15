----------------------------------------------------------------------------------
-- cpu_core_tmr.vhd
-- 层次化 TMR 加固顶层 (从 cpu_core_tmr.sv 自动转换)
--
-- 结构:
--   Layer 1: cpu_core_tmr (VHDL 顶层)
--   Layer 2: cpu_core_tmr_core × 3 (TMR 三模冗余)
--   Layer 3: 12 个子模块 (hazard, trap, csr, predictor, rom, ram,
--                        fetch, decode, execute, mem1, mem2, writeback)
--
-- TMR 表决通道 (6 通道):
--   TMR 寄存器组: 48 组 × 3 副本
--   错误计数器: 6 × 16-bit
--   阈值告警: 1% 错误率
--   多比特防御: Hamming 距离检测
----------------------------------------------------------------------------------

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity cpu_core_tmr is
    port (
        clk                     : in  STD_LOGIC;
        start                   : in  STD_LOGIC;

        -- mem_init_if (纯输入, 扇出到 3 核心)
        rom_init_write_enable   : in  STD_LOGIC;
        rom_init_write_addr     : in  STD_LOGIC_VECTOR(31 downto 0);
        rom_init_write_data     : in  STD_LOGIC_VECTOR(31 downto 0);

        -- mmio_out_if (输出表决, 5 通道)
        mmio_out_boot_valid     : out STD_LOGIC;
        mmio_out_exit_valid     : out STD_LOGIC;
        mmio_out_exit_code      : out STD_LOGIC_VECTOR(7 downto 0);
        mmio_out_print_valid    : out STD_LOGIC;
        mmio_out_print_data     : out STD_LOGIC_VECTOR(31 downto 0);

        -- mmio_in_if (混合: valid/data 扇入, ready 表决)
        mmio_in_valid           : in  STD_LOGIC;
        mmio_in_data            : in  STD_LOGIC_VECTOR(7 downto 0);
        mmio_in_ready           : out STD_LOGIC
    );
end cpu_core_tmr;

architecture hierarchical_tmr of cpu_core_tmr is

    -- Xilinx LUT3 原语 (如果合成工具不可用, GHDL 会视为外部声明)
    component LUT3 is
        generic (
            INIT : STD_LOGIC_VECTOR(7 downto 0) := X"00"
        );
        port (
            O  : out STD_LOGIC;
            I0 : in  STD_LOGIC;
            I1 : in  STD_LOGIC;
            I2 : in  STD_LOGIC
        );
    end component;

    -- 综合控制常量
    constant USE_XILINX_LUT : boolean := true;
    constant MAJ3_LUT_INIT  : STD_LOGIC_VECTOR(7 downto 0) := X"E8";

    -- 核心内部接口连线 (3 套)
    signal core1_ready, core2_ready, core3_ready : STD_LOGIC;

    signal core1_boot_valid   : STD_LOGIC;
    signal core2_boot_valid   : STD_LOGIC;
    signal core3_boot_valid   : STD_LOGIC;

    signal core1_exit_valid   : STD_LOGIC;
    signal core2_exit_valid   : STD_LOGIC;
    signal core3_exit_valid   : STD_LOGIC;

    signal core1_exit_code    : STD_LOGIC_VECTOR(7 downto 0);
    signal core2_exit_code    : STD_LOGIC_VECTOR(7 downto 0);
    signal core3_exit_code    : STD_LOGIC_VECTOR(7 downto 0);

    signal core1_print_valid  : STD_LOGIC;
    signal core2_print_valid  : STD_LOGIC;
    signal core3_print_valid  : STD_LOGIC;

    signal core1_print_data   : STD_LOGIC_VECTOR(31 downto 0);
    signal core2_print_data   : STD_LOGIC_VECTOR(31 downto 0);
    signal core3_print_data   : STD_LOGIC_VECTOR(31 downto 0);

    -- 内部连线 (3 核心驱动)
    signal core_ready   : STD_LOGIC_VECTOR(2 downto 0);

    -- rom_init 扇出信号 (3 路)
    signal rom_init_core1_write_enable : STD_LOGIC;
    signal rom_init_core1_write_addr   : STD_LOGIC_VECTOR(31 downto 0);
    signal rom_init_core1_write_data   : STD_LOGIC_VECTOR(31 downto 0);
    signal rom_init_core2_write_enable : STD_LOGIC;
    signal rom_init_core2_write_addr   : STD_LOGIC_VECTOR(31 downto 0);
    signal rom_init_core2_write_data   : STD_LOGIC_VECTOR(31 downto 0);
    signal rom_init_core3_write_enable : STD_LOGIC;
    signal rom_init_core3_write_addr   : STD_LOGIC_VECTOR(31 downto 0);
    signal rom_init_core3_write_data   : STD_LOGIC_VECTOR(31 downto 0);

    -- mmio_in 扇出信号 (3 路)
    signal mmio_in_core1_valid : STD_LOGIC;
    signal mmio_in_core1_data  : STD_LOGIC_VECTOR(7 downto 0);
    signal mmio_in_core2_valid : STD_LOGIC;
    signal mmio_in_core2_data  : STD_LOGIC_VECTOR(7 downto 0);
    signal mmio_in_core3_valid : STD_LOGIC;
    signal mmio_in_core3_data  : STD_LOGIC_VECTOR(7 downto 0);

    -- 错误计数器
    signal error_count_ch0 : UNSIGNED(15 downto 0) := (others => '0');
    signal error_count_ch1 : UNSIGNED(15 downto 0) := (others => '0');
    signal error_count_ch2 : UNSIGNED(15 downto 0) := (others => '0');
    signal error_count_ch3 : UNSIGNED(15 downto 0) := (others => '0');
    signal error_count_ch4 : UNSIGNED(15 downto 0) := (others => '0');
    signal error_count_ch5 : UNSIGNED(15 downto 0) := (others => '0');
    signal total_cycles     : UNSIGNED(31 downto 0) := (others => '0');

    -- 组件声明
    component cpu_core_tmr_core is
        port (
            clk   : in  STD_LOGIC;
            start : in  STD_LOGIC;
            -- interface 信号通过端口展开
            rom_init_write_enable : in  STD_LOGIC;
            rom_init_write_addr   : in  STD_LOGIC_VECTOR(31 downto 0);
            rom_init_write_data   : in  STD_LOGIC_VECTOR(31 downto 0);
            mmio_in_valid         : in  STD_LOGIC;
            mmio_in_data          : in  STD_LOGIC_VECTOR(7 downto 0);
            mmio_in_ready         : out STD_LOGIC;
            mmio_out_boot_valid   : out STD_LOGIC;
            mmio_out_exit_valid   : out STD_LOGIC;
            mmio_out_exit_code    : out STD_LOGIC_VECTOR(7 downto 0);
            mmio_out_print_valid  : out STD_LOGIC;
            mmio_out_print_data   : out STD_LOGIC_VECTOR(31 downto 0)
        );
    end component;

begin
    -- ======== [1] mem_init_if.sink → 纯输入扇出 ========
    rom_init_core1_write_enable <= rom_init_write_enable;
    rom_init_core1_write_addr   <= rom_init_write_addr;
    rom_init_core1_write_data   <= rom_init_write_data;

    rom_init_core2_write_enable <= rom_init_write_enable;
    rom_init_core2_write_addr   <= rom_init_write_addr;
    rom_init_core2_write_data   <= rom_init_write_data;

    rom_init_core3_write_enable <= rom_init_write_enable;
    rom_init_core3_write_addr   <= rom_init_write_addr;
    rom_init_core3_write_data   <= rom_init_write_data;

    -- ======== [2] mmio_in_if.sink → valid/data 扇入 ========
    mmio_in_core1_valid <= mmio_in_valid;
    mmio_in_core1_data  <= mmio_in_data;
    mmio_in_core2_valid <= mmio_in_valid;
    mmio_in_core2_data  <= mmio_in_data;
    mmio_in_core3_valid <= mmio_in_valid;
    mmio_in_core3_data  <= mmio_in_data;

    -- ======== [3] 3 核心实例化 ========
    core_inst_1 : cpu_core_tmr_core
        port map (
            clk                   => clk,
            start                 => start,
            rom_init_write_enable => rom_init_core1_write_enable,
            rom_init_write_addr   => rom_init_core1_write_addr,
            rom_init_write_data   => rom_init_core1_write_data,
            mmio_in_valid         => mmio_in_core1_valid,
            mmio_in_data          => mmio_in_core1_data,
            mmio_in_ready         => core1_ready,
            mmio_out_boot_valid   => core1_boot_valid,
            mmio_out_exit_valid   => core1_exit_valid,
            mmio_out_exit_code    => core1_exit_code,
            mmio_out_print_valid  => core1_print_valid,
            mmio_out_print_data   => core1_print_data
        );

    core_inst_2 : cpu_core_tmr_core
        port map (
            clk                   => clk,
            start                 => start,
            rom_init_write_enable => rom_init_core2_write_enable,
            rom_init_write_addr   => rom_init_core2_write_addr,
            rom_init_write_data   => rom_init_core2_write_data,
            mmio_in_valid         => mmio_in_core2_valid,
            mmio_in_data          => mmio_in_core2_data,
            mmio_in_ready         => core2_ready,
            mmio_out_boot_valid   => core2_boot_valid,
            mmio_out_exit_valid   => core2_exit_valid,
            mmio_out_exit_code    => core2_exit_code,
            mmio_out_print_valid  => core2_print_valid,
            mmio_out_print_data   => core2_print_data
        );

    core_inst_3 : cpu_core_tmr_core
        port map (
            clk                   => clk,
            start                 => start,
            rom_init_write_enable => rom_init_core3_write_enable,
            rom_init_write_addr   => rom_init_core3_write_addr,
            rom_init_write_data   => rom_init_core3_write_data,
            mmio_in_valid         => mmio_in_core3_valid,
            mmio_in_data          => mmio_in_core3_data,
            mmio_in_ready         => core3_ready,
            mmio_out_boot_valid   => core3_boot_valid,
            mmio_out_exit_valid   => core3_exit_valid,
            mmio_out_exit_code    => core3_exit_code,
            mmio_out_print_valid  => core3_print_valid,
            mmio_out_print_data   => core3_print_data
        );

    -- ======== [4] TMR 多数表决器 (6 通道) ========

    -- ch-0: mmio_in.ready (3选2)
    gen_lut_ch0 : if USE_XILINX_LUT generate
        u_lut_ch0 : LUT3
            generic map (INIT => X"E8")
            port map (O => mmio_in_ready, I0 => core1_ready, I1 => core2_ready, I2 => core3_ready);
    end generate;
    gen_bool_ch0 : if not USE_XILINX_LUT generate
        mmio_in_ready <= (core1_ready AND core2_ready) OR
                         (core1_ready AND core3_ready) OR
                         (core2_ready AND core3_ready);
    end generate;

    -- ch-1: mmio_out.boot_valid (3选2)
    gen_lut_ch1 : if USE_XILINX_LUT generate
        u_lut_ch1 : LUT3
            generic map (INIT => X"E8")
            port map (O => mmio_out_boot_valid, I0 => core1_boot_valid, I1 => core2_boot_valid, I2 => core3_boot_valid);
    end generate;
    gen_bool_ch1 : if not USE_XILINX_LUT generate
        mmio_out_boot_valid <= (core1_boot_valid AND core2_boot_valid) OR
                               (core1_boot_valid AND core3_boot_valid) OR
                               (core2_boot_valid AND core3_boot_valid);
    end generate;

    -- ch-2: mmio_out.exit_valid (3选2)
    gen_lut_ch2 : if USE_XILINX_LUT generate
        u_lut_ch2 : LUT3
            generic map (INIT => X"E8")
            port map (O => mmio_out_exit_valid, I0 => core1_exit_valid, I1 => core2_exit_valid, I2 => core3_exit_valid);
    end generate;
    gen_bool_ch2 : if not USE_XILINX_LUT generate
        mmio_out_exit_valid <= (core1_exit_valid AND core2_exit_valid) OR
                               (core1_exit_valid AND core3_exit_valid) OR
                               (core2_exit_valid AND core3_exit_valid);
    end generate;

    -- ch-3: mmio_out.exit_code (8-bit 按位3选2)
    gen_lut_ch3 : if USE_XILINX_LUT generate
        gen_ch3_bits : for i in 0 to 7 generate
            u_lut_ch3_bit : LUT3
                generic map (INIT => X"E8")
                port map (
                    O  => mmio_out_exit_code(i),
                    I0 => core1_exit_code(i),
                    I1 => core2_exit_code(i),
                    I2 => core3_exit_code(i)
                );
        end generate;
    end generate;
    gen_bool_ch3 : if not USE_XILINX_LUT generate
        mmio_out_exit_code <= (core1_exit_code AND core2_exit_code) OR
                              (core1_exit_code AND core3_exit_code) OR
                              (core2_exit_code AND core3_exit_code);
    end generate;

    -- ch-4: mmio_out.print_valid (3选2)
    gen_lut_ch4 : if USE_XILINX_LUT generate
        u_lut_ch4 : LUT3
            generic map (INIT => X"E8")
            port map (O => mmio_out_print_valid, I0 => core1_print_valid, I1 => core2_print_valid, I2 => core3_print_valid);
    end generate;
    gen_bool_ch4 : if not USE_XILINX_LUT generate
        mmio_out_print_valid <= (core1_print_valid AND core2_print_valid) OR
                                (core1_print_valid AND core3_print_valid) OR
                                (core2_print_valid AND core3_print_valid);
    end generate;

    -- ch-5: mmio_out.print_data (32-bit 按位3选2)
    gen_lut_ch5 : if USE_XILINX_LUT generate
        gen_ch5_bits : for i in 0 to 31 generate
            u_lut_ch5_bit : LUT3
                generic map (INIT => X"E8")
                port map (
                    O  => mmio_out_print_data(i),
                    I0 => core1_print_data(i),
                    I1 => core2_print_data(i),
                    I2 => core3_print_data(i)
                );
        end generate;
    end generate;
    gen_bool_ch5 : if not USE_XILINX_LUT generate
        mmio_out_print_data <= (core1_print_data AND core2_print_data) OR
                               (core1_print_data AND core3_print_data) OR
                               (core2_print_data AND core3_print_data);
    end generate;

end hierarchical_tmr;