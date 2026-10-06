import os
import glob
import pandas as pd
import numpy as np

def analyze_chat(file_path):
    if not os.path.exists(file_path): return None
    df = pd.read_csv(file_path)
    if len(df) == 0: return None
    
    # Calculate P50, P95, P99
    ret_p50 = df['retrieval_latency_ms'].quantile(0.50)
    ret_p95 = df['retrieval_latency_ms'].quantile(0.95)
    ret_p99 = df['retrieval_latency_ms'].quantile(0.99)
    
    e2e_p50 = df['e2e_latency_ms'].quantile(0.50)
    e2e_p95 = df['e2e_latency_ms'].quantile(0.95)
    e2e_p99 = df['e2e_latency_ms'].quantile(0.99)
    
    total_time = df['e2e_latency_ms'].sum() / 1000.0
    throughput = len(df) / total_time if total_time > 0 else 0
    failure_rate = (len(df[df['success'] == False]) / len(df)) * 100
    
    return {
        'ret_p50': ret_p50, 'ret_p95': ret_p95, 'ret_p99': ret_p99,
        'e2e_p50': e2e_p50, 'e2e_p95': e2e_p95, 'e2e_p99': e2e_p99,
        'throughput': throughput, 'failure_rate': failure_rate
    }

def analyze_ingestion(file_path):
    if not os.path.exists(file_path): return None
    df = pd.read_csv(file_path)
    if len(df) == 0: return None
    return df.iloc[0].to_dict()

def analyze_resources(file_path):
    if not os.path.exists(file_path): return None
    df = pd.read_csv(file_path)
    if len(df) == 0: return None
    return df.iloc[0].to_dict()

def main():
    results = {}
    for arch in ['cloud', 'dbms']:
        results[arch] = {
            'paper_chat': analyze_chat(f'benchmark/results/raw/{arch}_paper_chat.csv'),
            'project_chat': analyze_chat(f'benchmark/results/raw/{arch}_project_chat.csv'),
            'ingestion': analyze_ingestion(f'benchmark/results/raw/{arch}_ingestion.csv'),
            'resources': analyze_resources(f'benchmark/results/raw/{arch}_resources.csv')
        }
        
    # Generate Markdown Tables
    md = "# SAIRA Benchmark Results\n\n"
    
    # Table 1: Paper Chat
    md += "### TABLE 1: Paper Chat performance\n\n"
    md += "| Architecture | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Failure % |\n"
    md += "|---|---|---|---|---|---|\n"
    for arch in ['dbms', 'cloud']:
        res = results[arch]['paper_chat']
        if res:
            md += f"| {arch} | {res['ret_p50']:.1f} | {res['ret_p95']:.1f} | {res['ret_p99']:.1f} | {res['throughput']:.2f} | {res['failure_rate']:.1f} |\n"
            
    # Table 2: Project Chat
    md += "\n### TABLE 2: Project Chat performance\n\n"
    md += "| Architecture | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Failure % |\n"
    md += "|---|---|---|---|---|---|\n"
    for arch in ['dbms', 'cloud']:
        res = results[arch]['project_chat']
        if res:
            md += f"| {arch} | {res['ret_p50']:.1f} | {res['ret_p95']:.1f} | {res['ret_p99']:.1f} | {res['throughput']:.2f} | {res['failure_rate']:.1f} |\n"

    # Table 3: Resource Utilization
    md += "\n### TABLE 3: Resource utilization\n\n"
    md += "| Architecture | CPU Avg (%) | CPU Peak (%) | Memory Avg (MB) | Memory Peak (MB) |\n"
    md += "|---|---|---|---|---|\n"
    for arch in ['dbms', 'cloud']:
        res = results[arch]['resources']
        if res:
            md += f"| {arch} | {res['cpu_avg']:.1f} | {res['cpu_peak']:.1f} | {res['mem_avg_mb']:.0f} | {res['mem_peak_mb']:.0f} |\n"

    # Table 4: Ingestion
    md += "\n### TABLE 4: Ingestion\n\n"
    md += "| Architecture | Corpus | Total Time (s) | Time/Paper (s) |\n"
    md += "|---|---|---|---|\n"
    for arch in ['dbms', 'cloud']:
        res = results[arch]['ingestion']
        if res:
            md += f"| {arch} | {res['corpus_size']} | {res['total_time_s']:.1f} | {res['time_per_paper_s']:.1f} |\n"

    os.makedirs('benchmark/tables', exist_ok=True)
    with open('benchmark/tables/results.md', 'w') as f:
        f.write(md)
        
    print("Generated benchmark/tables/results.md")

if __name__ == '__main__':
    main()
