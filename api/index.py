from flask import Flask, request, jsonify, render_template
import pandas as pd
import io

app = Flask(__name__)

# @app.route('/')
# def index():
#     return render_template('index.html')

@app.route('/api/aggregate', methods=['POST'])
def aggregate_csv():
    uploaded_files = request.files.getlist('csv_files')
    
    if not uploaded_files:
        return jsonify({'error': 'ファイルがアップロードされていません。'}), 400

    combined_df_list = []

    for file in uploaded_files:
        try:
            # Shift-JIS (cp932) エンコーディングでファイルを読み込みます
            df = pd.read_csv(io.StringIO(file.stream.read().decode('cp932')))

            # 複数のCSV形式に対応するためのロジック
            if '数量' in df.columns:
                df_clean = df[['商品名', '数量']].copy()
            elif '分量' in df.columns:
                df_clean = df[['商品名']].copy()
                df_clean['数量'] = 1
            elif '商品名' in df.columns:
                df_clean = df[['商品名']].copy()
                df_clean['数量'] = 1
            else:
                # 必要な列が見つからない場合はこのファイルをスキップ
                continue

            df_clean.columns = ['商品名', '数量']
            combined_df_list.append(df_clean)

        except Exception as e:
            print(f"ファイルの処理中にエラーが発生しました: {e}")
            return jsonify({'error': 'ファイルの読み込みに失敗しました。'}), 500

    if not combined_df_list:
        return jsonify({'error': '処理できるデータがありませんでした。'}), 400

    combined_df = pd.concat(combined_df_list, ignore_index=True)

    # 変更点：キーワードによる分類をせず、直接「商品名」で集計します
    aggregated_sales = combined_df.groupby('商品名')['数量'].sum().reset_index()

    # 列名を「合計数量」に統一します
    aggregated_sales.columns = ['商品名', '合計数量']

    result = aggregated_sales.to_dict('records')

    return jsonify({'result': result})

if __name__ == '__main__':
    app.run(debug=True)