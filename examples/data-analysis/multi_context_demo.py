#!/usr/bin/env python3
"""
Agent Sandbox沙箱能力展示
展示复杂场景下的多Context协作: 数据预处理 + 分析 + 可视化
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 设置环境变量（可通过环境变量预先设置，或在此处直接修改）
if not os.getenv('E2B_DOMAIN'):
    os.environ['E2B_DOMAIN'] = 'tencentags.com'
if not os.getenv('E2B_API_KEY'):
    # E2B_API_KEY should be obtained from Tencent Cloud Agent Sandbox product
    os.environ['E2B_API_KEY'] = 'your_api_key'

def create_complex_demo_data():
    print("创建演示数据集, 总数5000条")
    np.random.seed(42)
    
    # 生成电商数据
    n_products = 5000
    categories = ['Electronics', 'Clothing', 'Books', 'Home & Garden', 'Sports', 'Beauty', 'Automotive']
    regions = ['North America', 'Europe', 'Asia Pacific', 'Latin America', 'Middle East', 'Africa']
    
    # 生成时间序列数据
    start_date = datetime.now() - timedelta(days=365)
    dates = [start_date + timedelta(days=x) for x in range(365)]
    
    # 先生成价格，然后基于价格生成合理的成本
    prices = np.random.lognormal(3, 0.8, n_products).round(2)
    
    # 成本设定为价格的50-85%
    cost_ratios = np.random.uniform(0.5, 0.85, n_products)
    costs = (prices * cost_ratios).round(2)
    
    data = {
        'product_id': [f'SKU_{i:05d}' for i in range(1, n_products + 1)],
        'product_name': [f'Product_{i}' for i in range(1, n_products + 1)],
        'category': np.random.choice(categories, n_products),
        'region': np.random.choice(regions, n_products),
        'price': prices,
        'cost': costs,
        'sales_count': np.random.poisson(15, n_products),
        'customer_rating': np.random.beta(8, 2, n_products) * 4 + 1,
        'discount_rate': np.random.exponential(0.1, n_products).clip(0, 0.5),
        'launch_date': np.random.choice(dates, n_products),
        'supplier_id': np.random.randint(1, 50, n_products),
        'weight_kg': np.random.lognormal(0, 1, n_products).round(2),
        'is_premium': np.random.choice([True, False], n_products, p=[0.2, 0.8]),
        'marketing_spend': np.random.gamma(2, 50, n_products).round(2),
        'return_rate': np.random.beta(1, 20, n_products),
    }
    
    df = pd.DataFrame(data)
    
    # 计算衍生字段
    df['revenue'] = df['price'] * df['sales_count'] * (1 - df['discount_rate'])
    df['profit'] = df['revenue'] - (df['cost'] * df['sales_count'])
    df['profit_margin'] = df['profit'] / df['revenue']
    df['days_since_launch'] = (datetime.now() - df['launch_date']).dt.days
    df['roi'] = df['profit'] / df['marketing_spend']
    
    # 添加季节性因素
    df['launch_month'] = df['launch_date'].dt.month
    df['launch_quarter'] = df['launch_date'].dt.quarter
    df['is_holiday_season'] = df['launch_month'].isin([11, 12])
    
    df.to_csv('complex_demo_data.csv', index=False)
    print(f"演示数据已创建: {len(df)} 个产品, {len(categories)} 个类别, {len(regions)} 个地区")
    return 'complex_demo_data.csv'


# Context 1: 数据预处理专家代码
def get_preprocessing_code():
    """返回数据预处理专家的代码"""
    return '''
import pandas as pd
import numpy as np
from datetime import datetime
import json

print("数据预处理专家开始工作...")

# 读取复杂数据
df = pd.read_csv('/tmp/complex_input_data.csv')
df['launch_date'] = pd.to_datetime(df['launch_date'])

print(f"原始数据: {len(df)} 行, {len(df.columns)} 列")

# 设置专家专属变量
preprocessing_expert_id = "DATA_PREP_001"
processing_timestamp = datetime.now().isoformat()

print(f"预处理专家ID: {preprocessing_expert_id}")

# 数据质量检查和清洗
df_cleaned = df.copy()
df_cleaned['customer_rating'] = df_cleaned['customer_rating'].clip(1, 5)

# 移除亏损产品：删除利润率小于0的产品（企业会停产亏损产品）
original_count = len(df_cleaned)
negative_profit_count = (df_cleaned['profit_margin'] < 0).sum()
df_cleaned = df_cleaned[df_cleaned['profit_margin'] >= 0].copy()
cleaned_count = len(df_cleaned)

print(f"数据清洗统计:")
print(f"  原始产品数量: {original_count}")
print(f"  移除亏损产品: {negative_profit_count} 个")
print(f"  保留盈利产品: {cleaned_count} 个")
print(f"  数据保留率: {cleaned_count/original_count*100:.1f}%")
print(f"  清洗后利润率范围: {df_cleaned['profit_margin'].min():.3f} 到 {df_cleaned['profit_margin'].max():.3f}")

# 特征工程
df_cleaned['price_tier'] = pd.cut(df_cleaned['price'], 
                                 bins=[0, 20, 50, 100, 500, float('inf')], 
                                 labels=['Budget', 'Economy', 'Mid-range', 'Premium', 'Luxury'])

df_cleaned['performance_score'] = (
    df_cleaned['customer_rating'] * 0.3 + 
    df_cleaned['sales_count'] / df_cleaned['sales_count'].max() * 5 * 0.4 +
    (1 - df_cleaned['return_rate']) * 5 * 0.3
)

print(f"数据清洗完成! 新增特征: price_tier, performance_score")

# 保存清洗后的数据
df_cleaned.to_csv('/tmp/cleaned_data.csv', index=False)

# 生成数据质量报告
quality_report = {
    'expert_info': {
        'expert_id': preprocessing_expert_id,
        'processing_timestamp': processing_timestamp
    },
    'data_summary': {
        'total_records': len(df_cleaned),
        'new_features': ['price_tier', 'performance_score']
    }
}

with open('/tmp/data_quality_report.json', 'w') as f:
    json.dump(quality_report, f, indent=2, default=str)

print("已保存: cleaned_data.csv, data_quality_report.json")
print("数据预处理专家工作完成！")
'''


# Context 2: 高级分析师代码
def get_analysis_code():
    """返回高级数据分析师的代码"""
    return '''
import pandas as pd
import numpy as np
import json
from datetime import datetime

print("高级数据分析师开始工作...")

try:
    from scipy import stats
    scipy_available = True
except ImportError:
    scipy_available = False

# 验证环境隔离
print("=== 环境隔离验证 ===")
try:
    print(f"尝试访问Context 1的变量 'preprocessing_expert_id': {preprocessing_expert_id}")
    print("隔离失败！能够访问其他Context的变量")
except NameError:
    print("尝试访问Context 1的变量 'preprocessing_expert_id'")
    print("无法访问Context 1的变量 - 环境隔离成功！")

# 设置分析师专属变量
analyst_expert_id = "ANALYST_002"

# 读取清洗后的数据
try:
    df = pd.read_csv('/tmp/cleaned_data.csv')
    df['launch_date'] = pd.to_datetime(df['launch_date'])
    print(f"分析数据: {len(df)} 行记录")
    print(f"数据列: {list(df.columns)}")
except Exception as e:
    print(f"读取数据文件失败: {e}")
    exit(1)

# 高级统计分析
try:
    print("开始类别分析...")
    category_analysis = df.groupby('category').agg({
        'revenue': ['sum', 'mean'],
        'profit_margin': 'mean',
        'customer_rating': 'mean'
    }).round(2)
    print("类别分析完成")
except Exception as e:
    print(f"类别分析失败: {e}")
    category_analysis = None

try:
    print("开始地区分析...")
    region_analysis = df.groupby('region').agg({
        'revenue': ['sum', 'mean'],
        'profit_margin': 'mean'
    }).round(2)
    print("地区分析完成")
except Exception as e:
    print(f"地区分析失败: {e}")
    region_analysis = None

# 相关性分析
try:
    print("开始相关性分析...")
    correlation_columns = ['price', 'sales_count', 'customer_rating', 'profit_margin', 'marketing_spend', 'roi']
    available_columns = [col for col in correlation_columns if col in df.columns]
    print(f"可用的相关性分析列: {available_columns}")
    
    correlation_matrix = df[available_columns].corr()
    print("相关性分析完成")
except Exception as e:
    print(f"相关性分析失败: {e}")
    correlation_matrix = None

# 找出最佳表现产品
try:
    print("开始寻找最佳表现产品...")
    if 'performance_score' in df.columns:
        top_performers = df.nlargest(10, 'performance_score')[['product_name', 'category', 'performance_score', 'revenue']]
        print("最佳表现产品分析完成")
    else:
        print("警告: performance_score列不存在，使用revenue作为替代")
        top_performers = df.nlargest(10, 'revenue')[['product_name', 'category', 'revenue']]
except Exception as e:
    print(f"最佳表现产品分析失败: {e}")
    top_performers = None

# 统计显著性检验
statistical_tests = {}
if scipy_available:
    try:
        print("开始统计显著性检验...")
        category_revenue_groups = [group['revenue'].values for name, group in df.groupby('category')]
        f_stat, p_value = stats.f_oneway(*category_revenue_groups)
        statistical_tests = {
            'category_revenue_anova': {
                'f_statistic': float(f_stat),
                'p_value': float(p_value),
                'significant': p_value < 0.05
            }
        }
        print("统计显著性检验完成")
    except Exception as e:
        print(f"统计显著性检验失败: {e}")
        statistical_tests = {'error': str(e)}
else:
    statistical_tests = {'note': 'scipy不可用，跳过统计检验'}

# 生成分析报告
try:
    print("生成分析报告...")
    analysis_report = {
        'analyst_info': {
            'analyst_id': analyst_expert_id,
            'analysis_timestamp': datetime.now().isoformat()
        },
        'statistical_tests': statistical_tests,
        'key_insights': {
            'avg_customer_satisfaction': float(df['customer_rating'].mean()),
            'total_market_value': float(df['revenue'].sum()),
            'total_products': len(df)
        }
    }
    
    # 只添加成功的分析结果
    if category_analysis is not None:
        # 将MultiIndex转换为字符串键
        category_dict = {}
        for col in category_analysis.columns:
            if isinstance(col, tuple):
                key = '_'.join(str(x) for x in col)
            else:
                key = str(col)
            category_dict[key] = category_analysis[col].to_dict()
        analysis_report['category_analysis'] = category_dict
        analysis_report['key_insights']['top_revenue_category'] = category_analysis['revenue']['sum'].idxmax()
    
    if region_analysis is not None:
        # 将MultiIndex转换为字符串键
        region_dict = {}
        for col in region_analysis.columns:
            if isinstance(col, tuple):
                key = '_'.join(str(x) for x in col)
            else:
                key = str(col)
            region_dict[key] = region_analysis[col].to_dict()
        analysis_report['region_analysis'] = region_dict
        analysis_report['key_insights']['most_profitable_region'] = region_analysis['profit_margin']['mean'].idxmax()
    
    if correlation_matrix is not None:
        analysis_report['correlation_matrix'] = correlation_matrix.to_dict()
    
    if top_performers is not None:
        analysis_report['top_performers'] = top_performers.to_dict('records')

    with open('/tmp/analysis_report.json', 'w') as f:
        json.dump(analysis_report, f, indent=2, default=str)
    
    print("分析报告已保存")
except Exception as e:
    print(f"生成分析报告失败: {e}")

print("高级数据分析师工作完成！")

# 显示关键洞察
try:
    insights = analysis_report['key_insights']
    print("=== 关键洞察 ===")
    if 'top_revenue_category' in insights:
        print(f"收入冠军类别: {insights['top_revenue_category']}")
    if 'most_profitable_region' in insights:
        print(f"最盈利地区: {insights['most_profitable_region']}")
    print(f"平均客户满意度: {insights['avg_customer_satisfaction']:.2f}")
    print(f"市场总价值: ${insights['total_market_value']:,.2f}")
    print(f"产品总数: {insights['total_products']}")
except Exception as e:
    print(f"显示关键洞察失败: {e}")
'''


# Context 3: 可视化大师代码
def get_visualization_code():
    """返回数据可视化大师的代码"""
    return '''
import pandas as pd
import numpy as np
import json

print("数据可视化大师开始创作...")

# 设置matplotlib后端（非交互式）
try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非交互式后端
    import matplotlib.pyplot as plt
    import seaborn as sns
    print("matplotlib和seaborn导入成功")
except ImportError as e:
    print(f"导入matplotlib/seaborn失败: {e}")
    exit(1)

# 验证环境隔离
print("=== 环境隔离验证 ===")
isolation_tests = []

# 测试访问Context 1的变量
try:
    print(f"尝试访问Context 1的变量 'preprocessing_expert_id': {preprocessing_expert_id}")
    isolation_tests.append("能访问Context 1变量 - 隔离失败")
except NameError:
    print("尝试访问Context 1的变量 'preprocessing_expert_id'")
    print("无法访问Context 1的变量")
    isolation_tests.append("Context 1变量隔离成功")

# 测试访问Context 2的变量  
try:
    print(f"尝试访问Context 2的变量 'analyst_expert_id': {analyst_expert_id}")
    isolation_tests.append("能访问Context 2变量 - 隔离失败")
except NameError:
    print("尝试访问Context 2的变量 'analyst_expert_id'")
    print("无法访问Context 2的变量")
    isolation_tests.append("Context 2变量隔离成功")

print("--- 隔离测试汇总 ---")
for test in isolation_tests:
    print(f"  {test}")
print("Context 3环境完全隔离！")

# 设置可视化大师专属变量
viz_master_id = "VIZ_MASTER_003"

# 读取清洗前后的数据
try:
    print("开始读取数据文件...")
    df_original = pd.read_csv('/tmp/complex_input_data.csv')
    df_original['launch_date'] = pd.to_datetime(df_original['launch_date'])
    print("原始数据文件读取成功")
except Exception as e:
    print(f"读取原始数据文件失败: {e}")
    exit(1)

try:
    df_cleaned = pd.read_csv('/tmp/cleaned_data.csv')
    df_cleaned['launch_date'] = pd.to_datetime(df_cleaned['launch_date'])
    print("清洗后数据文件读取成功")
except Exception as e:
    print(f"读取清洗后数据文件失败: {e}")
    exit(1)

print(f"原始数据: {len(df_original)} 行记录")
print(f"清洗后数据: {len(df_cleaned)} 行记录")
print(f"数据减少: {len(df_original) - len(df_cleaned)} 行 ({(1-len(df_cleaned)/len(df_original))*100:.1f}%)")

# 创建数据清洗前后对比仪表板
try:
    print("开始创建对比仪表板...")
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))  # 减小图片尺寸
    fig.suptitle(f'数据清洗前后对比仪表板\\n原始:{len(df_original)}条 → 清洗后:{len(df_cleaned)}条 (移除{len(df_original)-len(df_cleaned)}条亏损产品)', 
                fontsize=16, fontweight='bold')

    # 1. 客户评分分布对比
    print("绘制客户评分分布对比...")
    ax1.hist(df_original['customer_rating'], bins=20, alpha=0.6, label='清洗前', color='red', edgecolor='black')
    ax1.hist(df_cleaned['customer_rating'], bins=20, alpha=0.6, label='清洗后', color='blue', edgecolor='black')
    ax1.set_xlabel('Customer Rating')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Customer Rating Distribution Comparison', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. 利润率分布对比
    print("绘制利润率分布对比...")
    ax2.hist(df_original['profit_margin'], bins=30, alpha=0.6, label='Before', color='red', range=(-2, 2))
    ax2.hist(df_cleaned['profit_margin'], bins=30, alpha=0.6, label='After', color='blue', range=(-2, 2))
    ax2.set_xlabel('Profit Margin')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Profit Margin Distribution Comparison', fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. 清洗前后数据质量统计
    print("绘制数据质量统计...")
    quality_stats = pd.DataFrame({
        'Before': [
            len(df_original),
            (df_original['profit_margin'] < 0).sum(),
            df_original['customer_rating'].min(),
            df_original.isnull().sum().sum()
        ],
        'After': [
            len(df_cleaned),
            (df_cleaned['profit_margin'] < 0).sum(),
            df_cleaned['customer_rating'].min(),
            df_cleaned.isnull().sum().sum()
        ]
    }, index=['Total Products', 'Loss Products', 'Min Rating', 'Missing Values'])

    quality_stats.plot(kind='bar', ax=ax3, color=['red', 'blue'], alpha=0.7)
    ax3.set_title('Data Quality Metrics Comparison', fontweight='bold')
    ax3.set_ylabel('Count')
    ax3.tick_params(axis='x', rotation=45)
    ax3.grid(True, alpha=0.3)

    # 4. 新增特征展示
    print("绘制价格分层特征...")
    if 'price_tier' in df_cleaned.columns:
        price_tier_counts = df_cleaned['price_tier'].value_counts()
        colors = plt.cm.Set3(np.linspace(0, 1, len(price_tier_counts)))
        ax4.pie(price_tier_counts.values, labels=price_tier_counts.index, autopct='%1.1f%%', colors=colors)
        ax4.set_title('Price Tier Distribution', fontweight='bold')
    else:
        ax4.text(0.5, 0.5, 'Price Tier Feature Not Generated', ha='center', va='center', transform=ax4.transAxes)
        ax4.set_title('Feature Status', fontweight='bold')

    plt.tight_layout()
    plt.savefig('/tmp/data_cleaning_comparison.png', dpi=200, bbox_inches='tight')  # 降低DPI
    plt.close()
    print("数据清洗对比仪表板已生成")
    
except Exception as e:
    print(f"创建对比仪表板失败: {e}")
    import traceback
    traceback.print_exc()

# 创建综合仪表板（使用清洗后的数据）
try:
    print("开始创建综合仪表板...")
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))  # 进一步减小尺寸
    fig.suptitle('Agent Sandbox - Advanced Data Dashboard', fontsize=14, fontweight='bold')

    # 1. 类别收入分布
    print("绘制类别收入分布...")
    category_revenue = df_cleaned.groupby('category')['revenue'].sum().sort_values(ascending=False)
    colors = plt.cm.Set3(np.linspace(0, 1, len(category_revenue)))
    ax1.pie(category_revenue.values, labels=category_revenue.index, autopct='%1.1f%%', colors=colors)
    ax1.set_title('Revenue Distribution by Category', fontweight='bold')

    # 2. 地区表现热力图（简化版）
    print("绘制地区表现热力图...")
    region_metrics = df_cleaned.groupby('region').agg({
        'revenue': 'sum',
        'profit_margin': 'mean',
        'customer_rating': 'mean'
    }).round(2)

    # 简化热力图，直接显示数值
    sns.heatmap(region_metrics.T, annot=True, cmap='RdYlGn', fmt='.2f', ax=ax2)
    ax2.set_title('Regional Performance Heatmap', fontweight='bold')

    # 3. 价格vs销量散点图
    print("绘制价格销量散点图...")
    scatter = ax3.scatter(df_cleaned['price'], df_cleaned['sales_count'], c=df_cleaned['customer_rating'], 
                         s=30, alpha=0.6, cmap='viridis')  # 减小点的大小
    ax3.set_xlabel('Price ($)')
    ax3.set_ylabel('Sales Count')
    ax3.set_title('Price vs Sales Relationship', fontweight='bold')

    # 4. 利润率分布
    print("绘制利润率分布...")
    ax4.hist(df_cleaned['profit_margin'], bins=20, alpha=0.7, color='skyblue', edgecolor='black')  # 减少bins
    ax4.axvline(df_cleaned['profit_margin'].mean(), color='red', linestyle='--', 
               label=f'Mean: {df_cleaned["profit_margin"].mean():.2%}')
    ax4.set_xlabel('Profit Margin')
    ax4.set_ylabel('Frequency')
    ax4.set_title('Profit Margin Distribution', fontweight='bold')
    ax4.legend()

    plt.tight_layout()
    plt.savefig('/tmp/advanced_dashboard.png', dpi=150, bbox_inches='tight')  # 降低DPI
    plt.close()
    print("高级数据仪表板已生成")
    
except Exception as e:
    print(f"创建综合仪表板失败: {e}")
    import traceback
    traceback.print_exc()

# 创建相关性热力图
try:
    print("开始创建相关性热力图...")
    plt.figure(figsize=(8, 6))  # 减小尺寸
    
    # 检查列是否存在
    correlation_columns = ['price', 'sales_count', 'customer_rating', 'profit_margin', 'marketing_spend', 'roi']
    available_columns = [col for col in correlation_columns if col in df_cleaned.columns]
    print(f"可用的相关性分析列: {available_columns}")
    
    if len(available_columns) >= 2:
        correlation_data = df_cleaned[available_columns].corr()
        sns.heatmap(correlation_data, annot=True, cmap='RdBu_r', center=0, square=True, fmt='.2f')
        plt.title('Feature Correlation Matrix', fontsize=12, fontweight='bold')
        plt.tight_layout()
        plt.savefig('/tmp/correlation_heatmap.png', dpi=150, bbox_inches='tight')  # 降低DPI
        plt.close()
        print("相关性热力图已生成")
    else:
        print("可用列不足，跳过相关性热力图")
        
except Exception as e:
    print(f"创建相关性热力图失败: {e}")
    import traceback
    traceback.print_exc()

print("已生成可视化文件:")
print("data_cleaning_comparison.png - 数据清洗前后对比")
print("advanced_dashboard.png - 综合仪表板")
print("correlation_heatmap.png - 相关性分析")

print("数据可视化大师创作完成！")
'''

def enhanced_showcase_demo():
    try:
        # 创建复杂演示数据
        data_file = create_complex_demo_data()

        from e2b_code_interpreter import Sandbox
        import time

        start_time = time.time()
        sandbox = Sandbox.create(template="code-interpreter-v1")
        print(f"创建沙箱时间: {time.time() - start_time}")
        print(f"沙箱ID: {sandbox.sandbox_id}")
        print(f"沙箱状态: {sandbox.get_info()}")
        print(f"{sandbox._envd_access_token}")
        try:
            # 文件上传
            print("\n步骤1: 复杂数据文件上传")
            print("-" * 40)
            with open(data_file, 'r') as f:
                sandbox.files.write('/tmp/complex_input_data.csv', f)
            print("数据文件上传成功")
            
            # Context 1 - 数据预处理专家
            print("\nContext 1 - 数据预处理专家")
            print("-" * 40)
            
            context1 = sandbox.create_code_context()
            print(f"数据预处理专家工作环境: {context1.cwd}")
            
            sandbox.run_code(
                get_preprocessing_code(),
                context=context1,
                on_stdout=lambda data: print(f"[预处理专家] {data}"),
                on_stderr=lambda data: print(f"[预处理专家错误] {data}")
            )
            
            # Context 2: 高级分析师
            print("\nContext 2 - 高级数据分析师")
            print("-" * 40)
            
            context2 = sandbox.create_code_context()
            print(f"高级分析师工作环境: {context2.cwd}")
            
            sandbox.run_code(
                get_analysis_code(),
                context=context2,
                on_stdout=lambda data: print(f"[高级分析师] {data}"),
                on_stderr=lambda data: print(f"[高级分析师错误] {data}")
            )
            
            # Context 3: 可视化大师
            print("\nContext 3 - 数据可视化大师")
            print("-" * 40)
            
            context3 = sandbox.create_code_context()
            print(f"可视化大师工作环境: {context3.cwd}")
            
            sandbox.run_code(
                get_visualization_code(),
                context=context3,
                on_stdout=lambda data: print(f"[可视化大师] {data}"),
                on_stderr=lambda data: print(f"[可视化大师错误] {data}")
            )
            
            # 批量文件下载
            print("\n步骤2: 批量文件下载")
            print("-" * 40)
            
            os.makedirs('./enhanced_demo_output', exist_ok=True)
            
            download_files = [
                ('/tmp/complex_input_data.csv', './enhanced_demo_output/complex_input_data.csv'),
                ('/tmp/cleaned_data.csv', './enhanced_demo_output/cleaned_data.csv'),
                ('/tmp/data_quality_report.json', './enhanced_demo_output/data_quality_report.json'),
                ('/tmp/analysis_report.json', './enhanced_demo_output/analysis_report.json'),
                ('/tmp/data_cleaning_comparison.png', './enhanced_demo_output/data_cleaning_comparison.png'),
                ('/tmp/advanced_dashboard.png', './enhanced_demo_output/advanced_dashboard.png'),
                ('/tmp/correlation_heatmap.png', './enhanced_demo_output/correlation_heatmap.png')
            ]
            
            success_count = 0
            for remote_path, local_path in download_files:
                try:
                    content = sandbox.files.read(remote_path, format="bytes")
                    with open(local_path, 'wb') as f:
                        f.write(content)
                    print(f"下载成功: {local_path}")
                    success_count += 1
                except Exception as e:
                    print(f"下载失败: {remote_path} - {e}")
            
            print("成功展示的核心能力：")
            print("3个Context完全隔离 - 数据预处理→分析→可视化")
            print("复杂数据处理 - 5000个产品，7个类别，6个地区")
            print("数据清洗效果 - 清洗前后对比可视化")
            print("专业可视化 - 对比图表、仪表板、热力图等")
            print("实时流式输出 - 监控每个专家的工作进度")
            print("统计显著性分析 - ANOVA方差分析")
            print("完整文件流 - 上传→处理→下载")
            print(f"成功下载 {success_count}/{len(download_files)} 个文件")
            print("\n请查看 ./enhanced_demo_output/ 目录中的所有生成文件！")
            
        finally:
            sandbox.kill()
            print("沙箱已安全关闭")
            
    except Exception as e:
        print(f"演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    enhanced_showcase_demo()