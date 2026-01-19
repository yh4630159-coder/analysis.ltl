import streamlit as st
import pandas as pd
import io
import altair as alt # 引入高级绘图库

# ================= 1. 配置与映射 =================
COLUMN_MAPS = {
    'WP': { 
        'SKU': 'SKU', 'Warehouse': '仓库/Warehouse', 
        'Qty': '数量/Quantity', 'Fee': '金额/Amount', 
        'Age': '库龄/Library of Age', 'Vol': '体积(m³)',
        'Full_Name': 'WesternPost'
    },
    'LG': { 
        'SKU': '乐仓货品编码', 'Warehouse': '仓库', 
        'Qty': '数量', 'Fee': '计算金额', 
        'Age': '库龄', 'Vol': '总体积',
        'Full_Name': 'Lecangs'
    },
    'AI': { 
        'SKU': 'SKU', 'Warehouse': '仓库', 
        'Qty': '库存', 'Fee': '费用', 
        'Age': '在库天数', 'Vol': '立方数',
        'Full_Name': 'AI'
    },
    'WL': { 
        'SKU': '商品SKU', 'Warehouse': '实际发货仓库', 
        'Qty': '库存总数_QTY', 'Fee': '计费总价', 
        'Age': '库存库龄_CD', 'Vol': '计费总体积_立方米',
        'Full_Name': 'WWL'
    }
}

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 99999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 核心处理逻辑 =================

def parse_filename(filename):
    name_body = filename.rsplit('.', 1)[0]
    parts = name_body.split('_')
    
    if len(parts) >= 3:
        dept = parts[0]
        raw_code = parts[1].upper()
        provider_code = None
        for key in COLUMN_MAPS.keys():
            if key in raw_code:
                provider_code = key
                break
        date_str = parts[2]
        return dept, provider_code, date_str
    return None, None, None

def load_data_v3_2(file):
    # 1. 解析文件名
    dept, provider_code, date_str = parse_filename(file.name)
    
    if not dept:
        dept = "默认部门"
        for code in COLUMN_MAPS.keys():
            if code in file.name.upper():
                provider_code = code
                break
        date_str = "最新"

    if not provider_code:
        st.toast(f"⚠️ 跳过未知文件: {file.name}", icon="⏭️")
        return pd.DataFrame()

    # 2. 读取文件
    df = None
    try: df = pd.read_excel(file, engine='openpyxl', header=None); 
    except: pass
    if df is None:
        try: file.seek(0); df = pd.read_csv(file, encoding='utf-8', header=None)
        except: pass
    if df is None:
        try: file.seek(0); df = pd.read_csv(file, encoding='gb18030', header=None)
        except: pass
            
    if df is None:
        return pd.DataFrame()

    try:
        mapping = COLUMN_MAPS[provider_code]
        
        # 3. 智能表头定位
        header_idx = 0
        expected_cols = set(mapping.values())
        expected_cols.discard(mapping.get('Full_Name'))
        
        for i in range(min(20, len(df))):
            row_values = df.iloc[i].astype(str).str.strip().tolist()
            row_values = [x.replace('\ufeff', '') for x in row_values]
            match_count = sum(1 for x in row_values if x in expected_cols)
            if match_count >= 2:
                header_idx = i
                break
        
        new_columns = df.iloc[header_idx].astype(str).str.strip().str.replace('\ufeff', '')
        df = df.iloc[header_idx+1:].copy()
        df.columns = new_columns

        # 4. 清洗
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = cut_series.astype(str)
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        df['Age_Range'] = df['Age_Range'].str.strip()

        df['Dept'] = dept
        df['Provider'] = mapping['Full_Name']
        df['Date'] = date_str
        
        return df
        
    except Exception as e:
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存 BI V3.2", page_icon="📊", layout="wide")
st.title("📊 海外仓库存结构对比看板 (V3.2)")

with st.expander("ℹ️ 文件命名规范", expanded=False):
    st.markdown("请将文件重命名为：**`部门_服务商_日期.xlsx`** (例如: `业务一部_AI_2024-01.xlsx`)")

# --- 侧边栏 ---
with st.sidebar:
    st.header("📂 数据中心")
    uploaded_files = st.file_uploader("批量上传文件", type=['xlsx', 'xls', 'csv'], accept_multiple_files=True)
    
    dfs = []
    if uploaded_files:
        for file in uploaded_files:
            df = load_data_v3_2(file)
            if not df.empty:
                dfs.append(df)
        st.success(f"已加载 {len(dfs)} 个文件")

if not dfs:
    st.info("👈 请上传数据文件以开始分析")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    
    tab1, tab2 = st.tabs(["📊 单月详情 (SKU级)", "🆚 历史对比 (结构级)"])
    
    # ================= TAB 1: 详情分析 (保持 V2.7 逻辑) =================
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1: sel_dept = st.selectbox("选择部门", full_df['Dept'].unique(), key='t1_d')
        with c2: sel_date = st.selectbox("选择月份", sorted(full_df[full_df['Dept']==sel_dept]['Date'].unique(), reverse=True), key='t1_dt')
        with c3: sel_prov = st.selectbox("选择服务商", full_df[(full_df['Dept']==sel_dept)&(full_df['Date']==sel_date)]['Provider'].unique(), key='t1_p')
            
        target_df = full_df[(full_df['Dept']==sel_dept)&(full_df['Date']==sel_date)&(full_df['Provider']==sel_prov)]
        
        wh_list = sorted(target_df['Warehouse'].astype(str).unique().tolist())
        wh_list.insert(0, "全部汇总")
        sel_wh = st.selectbox("选择仓库", wh_list, key='t1_w')
        
        final_df = target_df if sel_wh == "全部汇总" else target_df[target_df['Warehouse'] == sel_wh]
        
        # 统计
        k1, k2, k3 = st.columns(3)
        k1.metric("总库存", f"{final_df['Qty'].sum():,.0f}")
        k2.metric("总体积", f"{final_df['Vol'].sum():,.2f} m³")
        k3.metric("总费用", f"${final_df['Fee'].sum():,.2f}")
        
        # 库龄表
        summary = final_df.groupby('Age_Range').agg({'Fee':'sum','Qty':'sum','Vol':'sum'}).reset_index()
        order_map = {l: i for i, l in enumerate(AGE_LABELS)}
        summary['sort'] = summary['Age_Range'].map(order_map).fillna(999)
        summary = summary.sort_values('sort').drop('sort', axis=1)
        summary['费用占比'] = (summary['Fee']/final_df['Fee'].sum()*100).fillna(0)
        
        st.dataframe(summary.style.format({'Fee':'${:.2f}','费用占比':'{:.1f}%'}), use_container_width=True)
        
        # Top 20
        st.divider()
        st.markdown("#### 🔍 异常库存深钻")
        valid_ages = [l for l in AGE_LABELS if l in final_df['Age_Range'].unique()]
        if valid_ages:
            rng = st.radio("选择库龄段", valid_ages, horizontal=True, index=len(valid_ages)-1, key='t1_r')
            drill = final_df[final_df['Age_Range'] == rng]
            if not drill.empty:
                top20 = drill.sort_values('Fee', ascending=False).head(20)[['SKU','Warehouse','Qty','Vol','Fee','Age']]
                try:
                    st.dataframe(top20.style.format({'Fee':'${:.2f}'}).background_gradient(subset=['Fee'], cmap='Reds'), use_container_width=True)
                except:
                    st.dataframe(top20, use_container_width=True)
            else: st.info("无数据")
        else: st.warning("无数据")

    # ================= TAB 2: 趋势对比 (V3.2 核心更新) =================
    with tab2:
        st.markdown("#### 🆚 库存结构与费用趋势对比")
        
        cc1, cc2, cc3 = st.columns(3)
        with cc1: t_dept = st.selectbox("分析部门", full_df['Dept'].unique(), key='t2_d')
        with cc2: t_prov = st.selectbox("分析服务商", full_df[full_df['Dept']==t_dept]['Provider'].unique(), key='t2_p')
        
        t_base = full_df[(full_df['Dept']==t_dept)&(full_df['Provider']==t_prov)]
        
        # 仓库筛选
        t_wh_list = sorted(t_base['Warehouse'].astype(str).unique().tolist())
        t_wh_list.insert(0, "全部汇总")
        with cc3: t_wh = st.selectbox("分析仓库", t_wh_list, key='t2_w')
        
        t_final = t_base if t_wh == "全部汇总" else t_base[t_base['Warehouse']==t_wh]
        
        # 日期筛选 (让用户决定对比哪几个月)
        available_dates = sorted(t_final['Date'].unique())
        selected_dates = st.multiselect("选择要对比的月份 (建议选2-3个)", available_dates, default=available_dates)
        
        if not selected_dates:
            st.warning("请至少选择一个月份进行分析。")
        else:
            # 过滤数据
            chart_df = t_final[t_final['Date'].isin(selected_dates)]
            
            # 聚合数据：按日期+库龄段
            agg_df = chart_df.groupby(['Date', 'Age_Range']).agg({
                'Qty': 'sum', 'Fee': 'sum', 'Vol': 'sum'
            }).reset_index()
            
            # --- 1. 库存量对比 (簇状柱形图) ---
            st.markdown("##### 📦 各库龄段库存量对比 (Quantity Comparison)")
            st.caption("👈 左侧是不同库龄段。不同颜色的柱子代表不同月份，方便对比同一库龄段下的库存变化。")
            
            # 使用 Altair 构建簇状柱形图
            base_chart = alt.Chart(agg_df).encode(
                x=alt.X('Age_Range', sort=AGE_LABELS, title="库龄分段"),
                y=alt.Y('Qty', title="库存数量 (PCS)"),
                color=alt.Color('Date', title="月份"),
                tooltip=['Date', 'Age_Range', 'Qty', 'Fee']
            )
            
            # xOffset 实现簇状效果
            grouped_bar = base_chart.mark_bar().encode(
                xOffset='Date'
            ).properties(height=400)
            
            st.altair_chart(grouped_bar, use_container_width=True)
            
            st.divider()
            
            # --- 2. 费用趋势 (堆叠柱状图) ---
            c_fee, c_vol = st.columns(2)
            
            with c_fee:
                st.markdown("##### 💰 费用结构趋势 (Fee Trend)")
                st.caption("不同颜色代表不同库龄段的费用贡献。")
                # 原生 bar_chart 自动堆叠
                # 数据透视: Index=Date, Columns=Age_Range, Values=Fee
                fee_pivot = agg_df.pivot(index='Date', columns='Age_Range', values='Fee')
                # 按照标准库龄顺序排序列
                sorted_cols = [c for c in AGE_LABELS if c in fee_pivot.columns]
                st.bar_chart(fee_pivot[sorted_cols])
                
            with c_vol:
                st.markdown("##### 📦 体积结构趋势 (Volume Trend)")
                st.caption("不同颜色代表不同库龄段的体积贡献。")
                vol_pivot = agg_df.pivot(index='Date', columns='Age_Range', values='Vol')
                sorted_cols = [c for c in AGE_LABELS if c in vol_pivot.columns]
                st.bar_chart(vol_pivot[sorted_cols])
                
            # --- 3. 详细数据表 ---
            st.markdown("##### 📋 详细对比数据")
            # 展示透视表：行=库龄，列=日期，值=费用/库存
            display_pivot = agg_df.pivot(index='Age_Range', columns='Date', values=['Qty', 'Fee'])
            # 排序行
            display_pivot = display_pivot.reindex(AGE_LABELS)
            st.dataframe(display_pivot.style.format("{:,.0f}", subset=pd.IndexSlice[:, pd.IndexSlice['Qty', :]])
                                          .format("${:,.2f}", subset=pd.IndexSlice[:, pd.IndexSlice['Fee', :]]), 
                         use_container_width=True)