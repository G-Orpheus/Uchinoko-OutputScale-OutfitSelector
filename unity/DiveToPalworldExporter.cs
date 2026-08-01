// DiveToPalworld用: アバターのprefabから変換に必要な一式を書き出す
//   - 統合FBX(NDMFベイク後・activeのみを1本に書き出したもの)
//   - humanoid.json (人型ボーン対応表、ベイク後の実体から)
//   - 各メッシュ×マテリアルスロットの実テクスチャ(PNG) + material_map.json
//
// 仕様(2026-07-21ぱん裁定): prefab→palは「そのプレハブをシーンに置いた時点での
// 見た目」を持ってくる。つまり:
//   - Inactiveなオブジェクト・無効なレンダラーは持ってこない
//   - Modular Avatarで着せた服(D&D構成)はNDMFベイク後の見た目で持ってくる
// このため元FBXのコピーではなく、ベイク済み実体を com.unity.formats.fbx の
// ModelExporter で1本のFBXへ統合書き出しする(複数FBX構成もこれで自然に解決)。
//
// 使い方(GUI):
//   1. このファイルを Assets/Editor/ に入れる(FBX Exporterパッケージ必須)
//   2. Projectビューでアバターのprefabを選択(またはHierarchyでルートを選択)
//   3. メニュー Tools > DiveToPalworld > Export Avatar
//   4. 出力フォルダごと DiveToPalworld へ(中のFBXをD&D)
//
// バッチ(開発用):
//   Unity.exe -batchmode -projectPath <proj> -executeMethod DiveToPalworldExporter.ExportBatch
//     -vrm2palPrefab <Assets/....prefab> -vrm2palOut <出力フォルダ> -quit
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class DiveToPalworldExporter
{
    [MenuItem("Tools/DiveToPalworld/Export Avatar")]
    static void ExportMenu()
    {
        var target = Selection.activeGameObject;
        if (target == null)
        {
            EditorUtility.DisplayDialog("DiveToPalworld",
                "アバターのprefab(またはHierarchyのルート)を選択してください", "OK");
            return;
        }
        string outDir = EditorUtility.SaveFolderPanel(
            "書き出し先フォルダ(空フォルダ推奨)", "", target.name + "_vrm2pal");
        if (string.IsNullOrEmpty(outDir)) return;
        try
        {
            Export(target, outDir);
            EditorUtility.DisplayDialog("DiveToPalworld",
                "書き出しました:\n" + outDir +
                "\n\nこのフォルダの中のFBXをDiveToPalworldへD&Dしてください", "OK");
            EditorUtility.RevealInFinder(outDir);
        }
        catch (Exception e)
        {
            EditorUtility.DisplayDialog("DiveToPalworld", "失敗: " + e.Message, "OK");
            Debug.LogException(e);
        }
    }

    // 開発・自動テスト用エントリポイント
    public static void ExportBatch()
    {
        string prefabPath = GetArg("-vrm2palPrefab");
        string outDir = GetArg("-vrm2palOut");
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        if (prefab == null) throw new Exception("prefabが読めない: " + prefabPath);
        Export(prefab, outDir);
        Debug.Log("D2P_EXPORT_DONE " + outDir);
    }

    static string GetArg(string name)
    {
        var args = Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        throw new Exception("引数が無い: " + name);
    }

    static void Export(GameObject target, string outDir)
    {
        Directory.CreateDirectory(outDir);
        // NDMFベイクとinactive除去で破壊的に変更するため、常に複製を処理する
        GameObject instance;
        if (target.scene.IsValid())
        {
            instance = UnityEngine.Object.Instantiate(target);
            instance.name = target.name;  // "(Clone)"を除去
        }
        else
        {
            instance = (GameObject)PrefabUtility.InstantiatePrefab(target);
            // 子の削除を許すため完全アンパック
            PrefabUtility.UnpackPrefabInstance(instance,
                PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
        }
        try
        {
            instance.SetActive(true);
            instance.transform.localPosition = Vector3.zero;      // 出力座標系を安定させる
            instance.transform.localRotation = Quaternion.identity;
            instance.transform.localScale = Vector3.one;
            D2PDiagDump(instance, "00 before StripNonWhitelistedPreBake");
            D2PDiagShot(instance, outDir, "00_front", "front");
            D2PDiagShot(instance, outDir, "00_side", "side");
            D2PDiagShot(instance, outDir, "00_isolated_beret_ribbon", "front", new[] { "Beret", "Ribbon", "Body" });
            StripNonWhitelistedPreBake(instance);                 // ①-a 第1段: VRC/MA/NDMF本体+必須5型以外を除去(BakeNdmfの直前必須)
            D2PDiagDump(instance, "01 after StripNonWhitelistedPreBake / before BakeNdmf");
            BakeNdmf(instance);                                   // ① MA等を適用
            D2PDiagDump(instance, "02 after BakeNdmf");
            D2PDiagShot(instance, outDir, "02_front", "front");
            D2PDiagShot(instance, outDir, "02_side", "side");
            D2PDiagShot(instance, outDir, "02_isolated_beret_ribbon", "front", new[] { "Beret", "Ribbon", "Body" });
            StripConstraints(instance);                           // ①' Constraint除去(輸出専用複製のみ)
            D2PDiagDump(instance, "03 after StripConstraints");
            StripInactive(instance);                              // ② 見えない物を除去
            D2PDiagDump(instance, "04 after StripInactive");
            D2PDiagShot(instance, outDir, "04_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            ConvertStaticMeshesToSkinned(instance);               // ②-a 非スキンメッシュをSkinnedMeshRenderer化(以降の全工程を一様化)
            D2PDiagDump(instance, "04b after ConvertStaticMeshesToSkinned");
            D2PDiagShot(instance, outDir, "04b_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            FlattenSkinnedMeshes(instance);                       // ②' 頂点をバインド時ワールドへ
            D2PDiagDump(instance, "05 after FlattenSkinnedMeshes");
            D2PDiagShot(instance, outDir, "05_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            BakeUniformScale(instance.transform, 1f);             // ②'' 階層スケール除去
            D2PDiagDump(instance, "06 after BakeUniformScale");
            D2PDiagShot(instance, outDir, "06_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            RebindToCurrent(instance);                            // ②''' bindposes再計算
            D2PDiagDump(instance, "07 after RebindToCurrent");
            D2PDiagShot(instance, outDir, "07_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            CollapseNestedArmatureContainers(instance);           // ②'''' wisker等ネストarmature対策(検証中)
            D2PDiagDump(instance, "08 after CollapseNestedArmatureContainers");
            D2PDiagShot(instance, outDir, "08_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            InsertSkeletonRootDummy(instance);                    // ②''''' eRoot対策(Hipsの上にダミー)
            D2PDiagDump(instance, "09 after InsertSkeletonRootDummy");
            D2PDiagShot(instance, outDir, "09_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            RedirectRootBonesAwayFromSelf(instance);              // ②'''''' eRoot対策(rootBone退避、汎用)
            D2PDiagDump(instance, "10 after RedirectRootBonesAwayFromSelf");
            D2PDiagShot(instance, outDir, "10_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            StripNonEssentialPostBake(instance);                  // ④-a 第2段: 必須5型以外を除去(ExportHumanoidの直前)
            D2PDiagDump(instance, "11 after StripNonEssentialPostBake");
            D2PDiagShot(instance, outDir, "11_isolated", "front", new[] { "Beret", "Ribbon", "Body" });
            ExportHumanoid(instance, outDir);                     // ③ ベイク後実体から
            string fbxName = ExportUnifiedFbx(instance, outDir);  // ④ 統合FBX
            ExportMaterials(instance, outDir, fbxName);           // ⑤ 実テクスチャ
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(instance);
        }
    }

    // ---- 一時診断(HZ班、位置バグ再調査用。原因特定後に削除する) ----
    static void D2PDiagDump(GameObject root, string label)
    {
        string[] names = { "Beret", "Ribbon", "SRB_AG1", "GameObject", "Head" };
        foreach (var n in names)
        {
            var matches = new List<Transform>();
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
                if (t.name == n) matches.Add(t);
            if (matches.Count == 0)
            {
                Debug.Log($"D2PDIAG2[{label}] {n}: NOT FOUND (0 matches)");
                continue;
            }
            if (matches.Count > 1)
                Debug.Log($"D2PDIAG2[{label}] {n}: {matches.Count} MATCHES(!)");
            foreach (var found in matches)
            {
                var mabp = found.GetComponent("ModularAvatarBoneProxy");
                Debug.Log($"D2PDIAG2[{label}] {n} @ {GetHierarchyPath(found)}: "
                    + $"active={found.gameObject.activeInHierarchy} "
                    + $"parent={found.parent?.name} localPos={found.localPosition:F5} "
                    + $"localScale={found.localScale:F5} worldPos={found.position:F5} "
                    + $"lossyScale={found.lossyScale:F5} hasBoneProxy={mabp != null}");
            }
        }
    }
    // カメラで撮影しPNG保存(比較用、目視確認目的)。dir: "front"/"back"/"side"
    // isolateNames!=null なら、その名前のRendererだけ見せて他は隠す(位置の一意特定用)
    static void D2PDiagShot(GameObject root, string outDir, string name, string dir = "back",
                             string[] isolateNames = null)
    {
        var renderers = root.GetComponentsInChildren<Renderer>(false);
        if (renderers.Length == 0) { Debug.Log("D2PDIAG2SHOT: no renderers"); return; }
        var savedEnabled = new List<(Renderer, bool)>();
        if (isolateNames != null)
        {
            foreach (var r in renderers)
            {
                savedEnabled.Add((r, r.enabled));
                r.enabled = Array.IndexOf(isolateNames, r.gameObject.name) >= 0;
            }
        }
        Bounds b = default; bool has = false;
        foreach (var r in renderers)
        {
            if (!r.enabled) continue;
            if (!has) { b = r.bounds; has = true; } else b.Encapsulate(r.bounds);
        }
        if (!has) { Debug.Log("D2PDIAG2SHOT: no visible renderers for " + name); goto restore; }

        {
            var camGo = new GameObject("D2PDiagCam");
            var cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.6f, 0.6f, 0.6f, 1f);
            float dist = Mathf.Max(b.extents.magnitude * 2.2f, 1f);
            Vector3 offset = dir == "front" ? new Vector3(0, 0, dist)
                            : dir == "side" ? new Vector3(dist, 0, 0)
                            : new Vector3(0, 0, -dist);
            camGo.transform.position = b.center + offset;
            camGo.transform.LookAt(b.center, Vector3.up);
            cam.nearClipPlane = 0.01f;
            cam.farClipPlane = dist * 4f;

            int w = 512, h = 768;
            var rt = new RenderTexture(w, h, 24);
            cam.targetTexture = rt;
            cam.Render();
            var prevActive = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prevActive;
            cam.targetTexture = null;
            rt.Release();

            var bytes = tex.EncodeToPNG();
            var path = Path.Combine(outDir, "d2pdiag_" + name + ".png");
            File.WriteAllBytes(path, bytes);
            Debug.Log("D2PDIAG2SHOT saved: " + path);

            UnityEngine.Object.DestroyImmediate(tex);
            UnityEngine.Object.DestroyImmediate(camGo);
        }
        restore:
        if (isolateNames != null)
            foreach (var (r, en) in savedEnabled) r.enabled = en;
    }
    // ---- 診断ここまで ----

    static Type FindType(string fullName)
    {
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            var t = asm.GetType(fullName);
            if (t != null) return t;
        }
        return null;
    }

    // 型がVRC公式(com.vrchat.*)/Modular Avatar/NDMF本体、または必須5型
    // (Transform/Animator/SkinnedMeshRenderer/MeshRenderer/MeshFilter)かどうかを
    // 判定する。名前空間のプレフィックス一致にすることで、SDK更新で型が増えても
    // 個別列挙なしに自動対応する。
    // 注意: Modular Avatarはパッケージ名がハイフン(nadena.dev.modular-avatar)だが
    // C#名前空間はアンダースコア(nadena.dev.modular_avatar)。ここを間違えると
    // MAコンポーネントを丸ごと消してベイクが壊れるため厳重に注意すること
    static bool IsWhitelistedComponentType(Type t)
    {
        if (t == typeof(Transform) || t == typeof(Animator)
            || t == typeof(SkinnedMeshRenderer) || t == typeof(MeshRenderer)
            || t == typeof(MeshFilter))
            return true;
        var ns = t.Namespace ?? "";
        return ns == "VRC" || ns.StartsWith("VRC.")
            || ns == "nadena.dev.modular_avatar" || ns.StartsWith("nadena.dev.modular_avatar.")
            || ns == "nadena.dev.ndmf" || ns.StartsWith("nadena.dev.ndmf.");
    }

    // ログ用: ルートからのHierarchyパス(Transform名を"/"で連結)
    static string GetHierarchyPath(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (var p = t.parent; p != null; p = p.parent)
            sb.Insert(0, p.name + "/");
        return sb.ToString();
    }

    // 第1段(ベイク前)ホワイトリスト。オーナー裁定「MA以外のNDMFプラグインは非対応」
    // を受け、VRC公式/Modular Avatar/NDMF本体/必須5型以外の**コンポーネントのみ**を
    // 全除去する(GameObjectそのものは消さない)。
    // 呼び出し位置は必ずBakeNdmfの"前"であること: NDMFのTransformingフェーズは
    // プラグインのマーカーコンポーネント(例: PoseClipperInstaller)をベイク実行時に
    // その場でスキャンするため(実データ確認済み)、BakeNdmfの後に置くと
    // 既にプラグインが実行済みになってしまい無効化の意味が無くなる。
    // 削除した型名+パスを1件ずつログに残す(取りこぼしの追跡・ユーザー問い合わせ対応用)
    static void StripNonWhitelistedPreBake(GameObject root)
    {
        int n = 0;
        foreach (var c in root.GetComponentsInChildren<Component>(true))
        {
            if (c == null) continue;  // missing script等
            var t = c.GetType();
            if (IsWhitelistedComponentType(t)) continue;
            string typeName = t.FullName;
            string path = GetHierarchyPath(c.transform);
            try
            {
                UnityEngine.Object.DestroyImmediate(c);
                n++;
                Debug.Log("D2P: [PreBakeサニタイズ] 除去: " + typeName + " @ " + path);
            }
            catch (Exception e)
            {
                Debug.LogWarning("D2P: [PreBakeサニタイズ] 除去失敗: " + typeName + " @ " + path
                                  + " (" + e.Message + ")");
            }
        }
        Debug.Log("D2P: PreBakeサニタイズ完了、" + n + "件除去"
                   + "(VRC公式/ModularAvatar/NDMF本体+Transform/Animator/SkinnedMeshRenderer/"
                   + "MeshRenderer/MeshFilter以外はすべて対象)");
    }

    // 第2段(ベイク後)ホワイトリスト。ベイク・各種ボーン処理が全て終わった後、
    // FBX輸出とhumanoid.json生成に必要な5型(Transform/Animator/
    // SkinnedMeshRenderer/MeshRenderer/MeshFilter)以外のコンポーネントを
    // 全除去する(GameObjectそのものは消さない)。
    // 呼び出し位置は必ずExportHumanoidの"前"であること。
    // 既存StripConstraints(IConstraint一括除去)とは独立で重複除去になるが、
    // 既存の安定した処理を壊さないため両方残す(実害なし)。
    // 削除した型名+パスを1件ずつログに残す
    static void StripNonEssentialPostBake(GameObject root)
    {
        int n = 0;
        foreach (var c in root.GetComponentsInChildren<Component>(true))
        {
            if (c == null) continue;
            var t = c.GetType();
            if (t == typeof(Transform) || t == typeof(Animator)
                || t == typeof(SkinnedMeshRenderer) || t == typeof(MeshRenderer)
                || t == typeof(MeshFilter))
                continue;
            string typeName = t.FullName;
            string path = GetHierarchyPath(c.transform);
            try
            {
                UnityEngine.Object.DestroyImmediate(c);
                n++;
                Debug.Log("D2P: [PostBakeサニタイズ] 除去: " + typeName + " @ " + path);
            }
            catch (Exception e)
            {
                Debug.LogWarning("D2P: [PostBakeサニタイズ] 除去失敗: " + typeName + " @ " + path
                                  + " (" + e.Message + ")");
            }
        }
        Debug.Log("D2P: PostBakeサニタイズ完了、" + n + "件除去"
                   + "(Transform/Animator/SkinnedMeshRenderer/MeshRenderer/MeshFilterのみ残す)");
    }

    // NDMF(Modular Avatar等の非破壊改変基盤)のベイクを実体へ適用する。
    // パッケージ参照を増やさないためreflectionで呼ぶ。未導入ならスキップ
    static void BakeNdmf(GameObject root)
    {
        var t = FindType("nadena.dev.ndmf.AvatarProcessor");
        if (t == null)
        {
            Debug.Log("D2P: NDMF未導入のためベイクをスキップ");
            return;
        }
        var mi = t.GetMethod("ProcessAvatar",
            BindingFlags.Public | BindingFlags.Static,
            null, new[] { typeof(GameObject) }, null);
        if (mi == null)
            throw new Exception("AvatarProcessor.ProcessAvatarが見つからない(NDMFのバージョン非互換)");
        mi.Invoke(null, new object[] { root });
        Debug.Log("D2P: NDMFベイク完了");
    }

    // Unity公式FBX Exporter(com.unity.formats.fbx@4.2.1)の
    // ModelExporter.ExportConstraints は特定の構成(2026-07-26実測: FaceEmo等
    // MA以外のNDMFプラグインが同居するsha-ta検体)で例外を投げ、輸出全体が失敗する。
    // Unityの制約コンポーネント(ParentConstraint/PositionConstraint/RotationConstraint/
    // ScaleConstraint/AimConstraint/LookAtConstraint、すべてIConstraint実装)は
    // 「Is Activeな間、毎フレーム計算結果を自身のTransformのローカル値へ直接
    // 上書きする」方式であり、コンポーネント自体は最終姿勢とは別の独立した
    // ポーズ情報を保持しない。つまりprefab保存時点でIs Activeなら、その時点の
    // Transformのローカル値は既に制約適用後の姿勢そのものであり、以降このメソッド内で
    // コンポーネントを消してもTransformの値自体はそのまま(このメソッドは
    // Transformの値を書き換えない)。この呼び出しはBakeNdmf直後・
    // FlattenSkinnedMeshes/BakeUniformScale/RebindToCurrent(いずれもボーンの
    // "現在の"ワールド行列を読むだけで、コンポーネントの有無を見ない)より前に
    // 置いているが、後続処理はTransformの現在値のみを参照するため順序に依存しない。
    // 除去は輸出用の一時複製(instance)に対してのみ行う——StripInactive等と同じ流儀
    static void StripConstraints(GameObject root)
    {
        int n = 0;
        foreach (var c in root.GetComponentsInChildren<UnityEngine.Animations.IConstraint>(true))
        {
            var comp = c as Component;
            if (comp == null) continue;
            UnityEngine.Object.DestroyImmediate(comp);
            n++;
        }
        if (n > 0)
            Debug.Log("D2P: Constraintコンポーネントを" + n + "件除去(Transform値は変更しない、輸出用複製のみ)");
    }

    // シーンに置いた時点で見えていない物(inactiveオブジェクト・無効レンダラー)を
    // 実体から除去する。ただしactiveなスキンメッシュが参照するボーンの階層は残す
    static void StripInactive(GameObject root)
    {
        var needed = new HashSet<Transform>();
        foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(false))
        {
            if (!r.enabled) continue;
            foreach (var b in r.bones)
                for (var t = b; t != null; t = t.parent) needed.Add(t);
            for (var t = r.rootBone; t != null; t = t.parent) needed.Add(t);
        }
        StripWalk(root.transform, needed);
    }

    static void StripWalk(Transform t, HashSet<Transform> needed)
    {
        var children = new List<Transform>();
        foreach (Transform c in t) children.Add(c);
        foreach (var c in children)
        {
            if (!c.gameObject.activeSelf)
            {
                if (ContainsAny(c, needed))
                {
                    // ボーンとして必要なので階層は残し、見た目だけ除去
                    foreach (var r in c.GetComponentsInChildren<Renderer>(true))
                        UnityEngine.Object.DestroyImmediate(r);
                    foreach (var mf in c.GetComponentsInChildren<MeshFilter>(true))
                        UnityEngine.Object.DestroyImmediate(mf);
                }
                else
                {
                    UnityEngine.Object.DestroyImmediate(c.gameObject);
                }
                continue;
            }
            var rend = c.GetComponent<Renderer>();
            if (rend != null && !rend.enabled)
            {
                UnityEngine.Object.DestroyImmediate(rend);
                var mf2 = c.GetComponent<MeshFilter>();
                if (mf2 != null) UnityEngine.Object.DestroyImmediate(mf2);
            }
            StripWalk(c, needed);
        }
    }

    static bool ContainsAny(Transform t, HashSet<Transform> set)
    {
        if (set.Contains(t)) return true;
        foreach (Transform c in t)
            if (ContainsAny(c, set)) return true;
        return false;
    }

    // スケール正規化後のボーンワールドで全SMRのbindposesを取り直す
    // (FlattenSkinnedMeshes→BakeUniformScaleの後に呼ぶ。メッシュ頂点は
    //  ワールド座標・ノードは恒等なので bindpose = worldToLocal で整合する)
    static void RebindToCurrent(GameObject root)
    {
        foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(false))
        {
            if (r.sharedMesh == null || r.bones == null || r.bones.Length == 0)
                continue;
            var bp = new Matrix4x4[r.bones.Length];
            for (int b = 0; b < r.bones.Length; b++)
                bp[b] = r.bones[b] != null
                    ? r.bones[b].worldToLocalMatrix : Matrix4x4.identity;
            r.sharedMesh.bindposes = bp;
        }
    }

    // 階層の一様スケール(VRChatリグのArmature=0.458等)をボーン位置へ焼き込み、
    // 全ノードをscale=1にする。ワールド位置は不変。回転は一様スケールなら不変。
    // 非一様スケールは対象外(警告のみ)
    static void BakeUniformScale(Transform t, float acc)
    {
        var ls = t.localScale;
        float s = (ls.x + ls.y + ls.z) / 3f;
        if (Mathf.Abs(ls.x - ls.y) > 1e-4f * Mathf.Abs(s)
            || Mathf.Abs(ls.x - ls.z) > 1e-4f * Mathf.Abs(s))
        {
            Debug.LogWarning("D2P: 非一様スケールは正規化できない: " + t.name
                             + " " + ls);
            return;  // この枝はそのまま(以降の子も触らない)
        }
        t.localPosition = t.localPosition * acc;
        float acc2 = acc * s;
        t.localScale = Vector3.one;

        // 非スキンメッシュ(MeshFilter直付け、帽子・リボン等のBone Proxyアクセサリ)対策
        // (2026-07-26実測、shapell_Osaki帽子/リボン位置バグの根本原因):
        // このメソッドは「ノード原点のワールド位置」を保つよう親のスケールを
        // 子のlocalPositionへ焼き込むが、メッシュ自身の頂点データ(原点から離れた
        // 位置にあることが多い。今回のケースでは累積1.43倍)へは何もしない。
        // SkinnedMeshRendererはFlattenSkinnedMeshes()で既にルート直下・恒等姿勢
        // (acc=1)へ変換済みなのでこの分岐に来ないが、非スキンのMeshFilterは
        // 素通りしてここへ来る。ノードのlocalScaleを1へ強制する代わりに、
        // 除去する分の累積スケール(acc2)をメッシュの頂点自体へ焼き込むことで、
        // 「ノード原点は同じ位置・頂点の実寸も同じ見た目」を両立する
        // (Unity上のRenderer.boundsで正しく見えている実際の見た目を、
        // スケール除去後も再現する)。
        var mf = t.GetComponent<MeshFilter>();
        if (mf != null && mf.sharedMesh != null && Mathf.Abs(acc2 - 1f) > 1e-6f)
        {
            var mesh = UnityEngine.Object.Instantiate(mf.sharedMesh);
            mesh.name = mf.sharedMesh.name;
            var verts = mesh.vertices;
            for (int i = 0; i < verts.Length; i++) verts[i] *= acc2;
            mesh.vertices = verts;
            mesh.RecalculateBounds();
            mf.sharedMesh = mesh;
            Debug.Log("D2P: BakeUniformScale: 非スキンメッシュへ累積スケール "
                       + acc2.ToString("F4") + " を頂点焼き込み: " + GetHierarchyPath(t));
        }

        foreach (Transform c in t)
            BakeUniformScale(c, acc2);
    }

    // 非スキンメッシュ(MeshFilter+MeshRenderer。帽子・リボン等、ボーンへ
    // Transform直付けする一般的なVRChatアクセサリ構成)を、その所属ボーンへ
    // 100%ウェイトのSkinnedMeshRendererへ変換する。
    // 狙い: 以降の全工程(FlattenSkinnedMeshes/BakeUniformScaleの頂点焼き込み/
    // chibi-fit/RebindToCurrent等)はSkinnedMeshRendererを前提に動くため、
    // 非スキンメッシュだけがそこから取り残され、体だけ変形して装飾品が
    // 置いていかれる(2026-07-26実測、shapell_Osakiのベレー帽・リボン)。
    // ここで一律SkinnedMeshRenderer化しておけば、後続処理が全メッシュへ
    // 一様に効く。
    // 所属ボーンはTransformの親をたどって特定する(NDMFベイク・
    // StripInactive後の階層は、アクセサリがボーンへ直接ぶら下がる構成に
    // なっている——Unity側は階層がそのままボーン構造を持つ)。
    // 親が無い(ルート直下)等で所属ボーンが特定できない場合は変換せず
    // そのまま残し、警告のみ出す(以降はBakeUniformScaleの頂点焼き込み
    // フォールバックに任せる)。
    // sharedMeshは複製してから加工し、元アセットには触らない。
    // 呼び出し位置はBakeNdmf後・FlattenSkinnedMeshes前が必須:
    // FlattenSkinnedMeshes以降の全処理はSkinnedMeshRendererのみを走査するため、
    // 変換はそれより前でなければ意味が無い。StripInactiveの後に置くことで、
    // 実際に書き出されるメッシュだけを変換対象へ絞れる。
    // 元からSkinnedMeshRendererのものには触らない
    // (SkinnedMeshRendererはMeshRendererを継承しないため、
    //  GetComponentsInChildren<MeshRenderer>では列挙されず自然に対象外になる)。
    static void ConvertStaticMeshesToSkinned(GameObject root)
    {
        // 変換中にコンポーネント構成を変えるため、対象を先に列挙してから処理する
        var targets = new List<MeshRenderer>(root.GetComponentsInChildren<MeshRenderer>(false));
        int n = 0, skipped = 0;
        foreach (var mr in targets)
        {
            var t = mr.transform;
            var mf = t.GetComponent<MeshFilter>();
            if (mf == null || mf.sharedMesh == null) continue;

            var bone = t.parent;
            if (bone == null)
            {
                Debug.LogWarning("D2P: [非スキン化] 所属ボーンが特定できない(親が無い): "
                                  + GetHierarchyPath(t) + "。変換せず残す");
                skipped++;
                continue;
            }

            var srcMesh = mf.sharedMesh;
            var mesh = UnityEngine.Object.Instantiate(srcMesh);
            mesh.name = srcMesh.name;

            var weights = new BoneWeight[mesh.vertexCount];
            for (int i = 0; i < weights.Length; i++)
                weights[i] = new BoneWeight { boneIndex0 = 0, weight0 = 1f };
            mesh.boneWeights = weights;
            // bindpose: 変換前と同じ見た目になるよう、
            // bone.localToWorld * bindpose == t.localToWorld を満たす行列を選ぶ
            // (非スキン時と同じワールド座標を、単一ボーンのスキニングで再現する)
            mesh.bindposes = new[] { bone.worldToLocalMatrix * t.localToWorldMatrix };

            var mats = mr.sharedMaterials;
            var wasEnabled = mr.enabled;

            UnityEngine.Object.DestroyImmediate(mr);
            UnityEngine.Object.DestroyImmediate(mf);

            var smr = t.gameObject.AddComponent<SkinnedMeshRenderer>();
            smr.sharedMesh = mesh;
            smr.bones = new[] { bone };
            smr.rootBone = bone;
            smr.sharedMaterials = mats;
            smr.enabled = wasEnabled;

            n++;
            Debug.Log("D2P: [非スキン化] MeshRenderer→SkinnedMeshRenderer変換(所属ボーン="
                       + bone.name + "): " + GetHierarchyPath(t));
        }
        if (n > 0 || skipped > 0)
            Debug.Log("D2P: 非スキンメッシュのSkinnedMeshRenderer変換完了、" + n + "件変換、"
                       + skipped + "件スキップ(所属ボーン特定不可)");
    }

    // Unityのスキニングはノード変換を無視してバインド行列で解決するが、Blenderの
    // FBXインポータはスキンメッシュをアーマチュア配下へローカル行列ごと付け替える
    // ため、ノード変換とバインドが食い違うリグ(Armatureスケール等)は
    // メッシュとスケルトンの大きさ・向きが合わなくなる(2026-07-22実測)。
    // → 頂点をバインド時ワールド座標へ変換した複製メッシュを作り、bindposesも
    //   現在のボーンワールドから再計算、ノードはルート直下の恒等に置く。
    //   これで「どの行列を信じるインポータ」でも同じ配置になる
    static void FlattenSkinnedMeshes(GameObject root)
    {
        foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(false))
        {
            if (r.sharedMesh == null || r.bones == null || r.bones.Length == 0)
                continue;
            var src = r.sharedMesh;
            var bp = src.bindposes;
            if (bp == null || bp.Length == 0 || r.bones[0] == null) continue;
            Matrix4x4 m = r.bones[0].localToWorldMatrix * bp[0];
            // 検算: 全ボーンで boneWorld×bindpose が一致するはず(未ポーズのrig)
            for (int b = 1; b < r.bones.Length && b < bp.Length; b++)
            {
                if (r.bones[b] == null) continue;
                Matrix4x4 mb = r.bones[b].localToWorldMatrix * bp[b];
                if ((mb.GetColumn(3) - m.GetColumn(3)).magnitude > 0.001f)
                {
                    Debug.LogWarning("D2P: バインド行列が不一致(ポーズ済みrig?): "
                                     + r.name + " bone " + b);
                    break;
                }
            }
            var mesh = UnityEngine.Object.Instantiate(src);
            mesh.name = src.name;
            var verts = mesh.vertices;
            var normals = mesh.normals;
            bool hasNormals = normals != null && normals.Length == verts.Length;

            // シーンで設定された現在のブレンドシェイプ値を頂点へ焼き込む。
            // MA構成では服をアバター体型に合わせるシェイプがシーン側で
            // 設定されていることが多い(toto実測: 未焼き込みだと服が体型に合わない)
            int baked = 0;
            for (int s = 0; s < mesh.blendShapeCount; s++)
            {
                float w = r.GetBlendShapeWeight(s);
                if (Mathf.Abs(w) < 1e-4f) continue;
                int frame = mesh.GetBlendShapeFrameCount(s) - 1;
                float fw = mesh.GetBlendShapeFrameWeight(s, frame);
                float k = fw > 1e-4f ? w / fw : w / 100f;
                var dv = new Vector3[verts.Length];
                var dn = new Vector3[verts.Length];
                mesh.GetBlendShapeFrameVertices(s, frame, dv, dn, null);
                for (int i = 0; i < verts.Length; i++)
                    verts[i] += dv[i] * k;
                if (hasNormals)
                    for (int i = 0; i < normals.Length; i++)
                        normals[i] += dn[i] * k;
                baked++;
            }
            if (baked > 0)
            {
                mesh.ClearBlendShapes();  // 焼き込み済み+deltasは座標変換しないため破棄
                Debug.Log("D2P: ブレンドシェイプ焼き込み: " + r.name + " " + baked + "件");
            }

            for (int i = 0; i < verts.Length; i++)
                verts[i] = m.MultiplyPoint3x4(verts[i]);
            mesh.vertices = verts;
            if (hasNormals)
            {
                Matrix4x4 nm = m.inverse.transpose;
                for (int i = 0; i < normals.Length; i++)
                    normals[i] = nm.MultiplyVector(normals[i]).normalized;
                mesh.normals = normals;
            }
            var newBp = new Matrix4x4[bp.Length];
            for (int b = 0; b < bp.Length; b++)
                newBp[b] = (b < r.bones.Length && r.bones[b] != null)
                    ? r.bones[b].worldToLocalMatrix : Matrix4x4.identity;
            mesh.bindposes = newBp;
            mesh.RecalculateBounds();
            r.sharedMesh = mesh;
            var t = r.transform;
            t.SetParent(root.transform, false);
            t.localPosition = Vector3.zero;
            t.localRotation = Quaternion.identity;
            t.localScale = Vector3.one;
        }
    }

    // FBX ExporterはスケルトンルートをeRootで書き、BlenderのFBXインポータは
    // eRootをアーマチュアオブジェクト化するためルートボーン(Hips)が消える
    // (2026-07-21実測)。Hipsの上に恒等ダミーを挟み、eRootをダミーへ吸わせる
    static void InsertSkeletonRootDummy(GameObject root)
    {
        var animator = root.GetComponentInChildren<Animator>();
        if (animator == null || animator.avatar == null || !animator.avatar.isHuman)
            return;
        var hips = animator.GetBoneTransform(HumanBodyBones.Hips);
        if (hips == null || hips.parent == null) return;
        var dummy = new GameObject("d2p_skeleton_root");
        dummy.transform.SetParent(hips.parent, false);
        dummy.transform.localPosition = Vector3.zero;
        dummy.transform.localRotation = Quaternion.identity;
        dummy.transform.localScale = Vector3.one;
        dummy.transform.SetSiblingIndex(hips.GetSiblingIndex());
        hips.SetParent(dummy.transform, true);
    }

    // 2026-07-26実測(FbxExporter.cs 3133-3155行): あるSkinnedMeshRendererの
    // rootBoneが「そのメッシュ自身のボーン」かつ「そのメッシュのbones[]に
    // 含まれる子ボーンを持つ」場合、そのボーンのFbxSkeletonはeRoot型で
    // 書き出される。BlenderのFBXインポータ(import_fbx.py find_armatures)は
    // eRoot型ノードを見つけるたびに独立したarmatureオブジェクトへ変換する
    // 仕様のため、Hipsだけでなく「各パーツ固有のrootBone」(実測: wiskerの
    // Head、PannAcc装飾品のBone等)でも同一の症状が起き、対応する
    // armature_setupエントリが無いままKeyErrorになる(InsertSkeletonRootDummy
    // でHipsの上にダミーを挟むだけでは、Hips自身のFbxSkeleton型は変わらず
    // 効かない。かつHips以外のrootBoneには元々対策していなかった)。
    // rootBoneは境界ボックス計算等にのみ使われスキニング結果には影響しない
    // ため、「自身のメッシュの子ボーンを持つrootBone」をすべてその親
    // (非ボーンの祖先。Hipsの場合はInsertSkeletonRootDummyが挿すダミー)へ
    // 差し替えることで、どのボーンもrootBone一致条件に該当しなくなり
    // eRootが一切付かなくなる(輸出用複製のみに適用、副作用なし)
    static void RedirectRootBonesAwayFromSelf(GameObject root)
    {
        int n = 0;
        foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
        {
            var rb = r.rootBone;
            if (rb == null || r.bones == null || rb.parent == null) continue;
            bool hasChildBoneInThisMesh = false;
            foreach (Transform c in rb)
            {
                if (Array.IndexOf(r.bones, c) >= 0) { hasChildBoneInThisMesh = true; break; }
            }
            if (!hasChildBoneInThisMesh) continue;
            r.rootBone = rb.parent;
            n++;
        }
        if (n > 0)
            Debug.Log("D2P: rootBoneを" + n + "件、自身の親へ退避(eRoot回避): ");
    }

    // Blenderのfind_armatures()は「ボーンではないNull/Root祖先」を見つけるたびに
    // 独立armatureへ変換するが、既にボーンチェーンの内部にネストされた非ボーン
    // コンテナ(子孫にボーンを持つNull)はこの走査経路(ボーン境界を跨がない
    // トップダウン探索)から構造的に外れてしまい、collect_armature_meshesの
    // 既知の集計漏れ(import_fbx.py内 "See T70244" コメント)でメッシュだけが
    // 親armatureのmeshes一覧に混入し、対応するarmature_setupが無いままKeyError
    // になる(2026-07-26実測、PanWisker/Armature/Head(内側)/WiskerParent_L…で発生)。
    // 該当コンテナ(自身はボーンではないが子孫にボーンを持ち、かつ祖先にも
    // ボーンがいる=ネストされたarmatureルート)を検出し、子を1段上へ直結して
    // コンテナ自体を消すことでボーンチェーンを途切れさせない。
    // ワールド座標は不変(worldPositionStays:trueで再親化するため見た目は無変化)。
    // 安全のためTransform以外の成分を持つオブジェクトは対象から除外する
    static void CollapseNestedArmatureContainers(GameObject root)
    {
        var bones = new HashSet<Transform>();
        foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
        {
            if (r.bones == null) continue;
            foreach (var b in r.bones)
                if (b != null) bones.Add(b);
        }
        if (bones.Count == 0) return;

        var all = new List<Transform>();
        CollectAllTransforms(root.transform, all);

        int n = 0;
        // 深い側(子)から処理するため末尾から辿る(親を先に潰すと判定がずれるため)
        for (int i = all.Count - 1; i >= 0; i--)
        {
            var t = all[i];
            if (t == root.transform) continue;
            if (bones.Contains(t)) continue;                   // 自身がボーンなら対象外
            if (t.GetComponents<Component>().Length > 1) continue; // Transform以外を持つなら触らない
            if (!HasAncestorBone(t, bones)) continue;          // ボーンチェーンの内部でなければ対象外
            if (!HasDescendantBone(t, bones)) continue;        // 子孫にボーンが無ければ対象外

            var parent = t.parent;
            var children = new List<Transform>();
            foreach (Transform c in t) children.Add(c);
            foreach (var c in children)
                c.SetParent(parent, true);                     // ワールド座標維持で1段上へ
            UnityEngine.Object.DestroyImmediate(t.gameObject);
            n++;
        }
        if (n > 0)
            Debug.Log("D2P: ネストされたarmatureコンテナを" + n + "件解消(ボーンチェーン直結)");
    }

    static void CollectAllTransforms(Transform t, List<Transform> outList)
    {
        outList.Add(t);
        foreach (Transform c in t) CollectAllTransforms(c, outList);
    }

    static bool HasAncestorBone(Transform t, HashSet<Transform> bones)
    {
        for (var p = t.parent; p != null; p = p.parent)
            if (bones.Contains(p)) return true;
        return false;
    }

    static bool HasDescendantBone(Transform t, HashSet<Transform> bones)
    {
        foreach (Transform c in t)
        {
            if (bones.Contains(c)) return true;
            if (HasDescendantBone(c, bones)) return true;
        }
        return false;
    }

    // com.unity.formats.fbx の ModelExporter でベイク後の実体を1本のFBXへ。
    // パッケージ参照を増やさないためreflectionで呼ぶ。
    // 重要: 既定のExportObject(string,Object)はASCII FBXを吐き、BlenderはASCII FBXを
    // 読めない(2026-07-21実測)。必ずBinary指定のオプションを組んで渡す
    static string ExportUnifiedFbx(GameObject go, string outDir)
    {
        var t = FindType("UnityEditor.Formats.Fbx.Exporter.ModelExporter");
        if (t == null)
            throw new Exception(
                "FBX Exporter(com.unity.formats.fbx)が未導入です。" +
                "export_from_unity.ps1経由で実行するか、Package Managerで追加してください");
        var safe = new StringBuilder();
        foreach (var ch in go.name)
            safe.Append(Array.IndexOf(Path.GetInvalidFileNameChars(), ch) >= 0 ? '_' : ch);
        string fbxName = safe + ".fbx";
        string path = Path.Combine(outDir, fbxName).Replace("\\", "/");

        // Binary指定オプション(4.x: 内部ExportModelSettingsSerialize / 5.x: 公開ExportModelOptions)
        object opts = null;
        foreach (var typeName in new[] {
            "UnityEditor.Formats.Fbx.Exporter.ExportModelOptions",
            "UnityEditor.Formats.Fbx.Exporter.ExportModelSettingsSerialize" })
        {
            var ot = t.Assembly.GetType(typeName);
            if (ot == null) continue;
            var candidate = Activator.CreateInstance(ot, true);
            if (SetFormatBinary(candidate)) { opts = candidate; break; }
        }
        if (opts == null)
            throw new Exception("FBX ExporterのBinary出力オプションを構築できない(バージョン非互換)");
        // Maya互換命名(スペースや.を_へ変換)を無効化。humanoid.jsonや製品FBXと
        // ボーン名が食い違う事故の元(2026-07-21実測: "Upper Leg.L"→"Upper_Leg_L")
        if (!TrySetOption(opts, "SetUseMayaCompatibleNames", "UseMayaCompatibleNames",
                          "mayaCompatibleNaming", false))
            Debug.LogWarning("D2P: Maya互換命名を無効化できなかった(ボーン名が変換される可能性)");

        // (string, 対象, ..., オプション, ...) を受けるExportObject/ExportObjectsを探して呼ぶ
        string result = null;
        bool invoked = false;
        foreach (var mi in t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static))
        {
            if (mi.Name != "ExportObject" && mi.Name != "ExportObjects") continue;
            var ps = mi.GetParameters();
            if (ps.Length < 3 || ps[0].ParameterType != typeof(string)) continue;
            int optIdx = -1;
            for (int i = 2; i < ps.Length; i++)
                if (ps[i].ParameterType.IsAssignableFrom(opts.GetType())) { optIdx = i; break; }
            if (optIdx < 0) continue;
            var args = new object[ps.Length];
            args[0] = path;
            if (ps[1].ParameterType == typeof(UnityEngine.Object[]))
                args[1] = new UnityEngine.Object[] { go };
            else if (ps[1].ParameterType.IsAssignableFrom(typeof(GameObject)))
                args[1] = go;
            else
                continue;
            args[optIdx] = opts;  // 残りの引数はnull(省略可能なDictionary等)
            result = mi.Invoke(null, args) as string;
            invoked = true;
            break;
        }
        if (!invoked)
            throw new Exception("ModelExporterのオプション付きExportが見つからない(バージョン非互換)");
        if (result == null || !File.Exists(path))
            throw new Exception("統合FBXの書き出しに失敗: " + path);
        // ASCIIで出ていないか検品(バイナリFBXは "Kaydara FBX Binary" マジックで始まる)
        var head = new byte[20];
        using (var fs = File.OpenRead(path)) fs.Read(head, 0, head.Length);
        if (Encoding.ASCII.GetString(head).IndexOf("Kaydara FBX Binary", StringComparison.Ordinal) != 0)
            throw new Exception("FBXがバイナリ形式になっていない(Blenderが読めないため中断)");
        return fbxName;
    }

    // オプションオブジェクトのExportFormatをBinaryへ(4.x/5.xの実装差をまとめて吸収)
    static bool SetFormatBinary(object opts)
    {
        const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        for (var t = opts.GetType(); t != null; t = t.BaseType)
        {
            var m = t.GetMethod("SetExportFormat", F);
            if (m != null && m.GetParameters().Length == 1)
            {
                m.Invoke(opts, new[] { EnumBinary(m.GetParameters()[0].ParameterType) });
                return true;
            }
            var p = t.GetProperty("ExportFormat", F);
            if (p != null && p.CanWrite && p.PropertyType.IsEnum)
            {
                p.SetValue(opts, EnumBinary(p.PropertyType), null);
                return true;
            }
            var f = t.GetField("exportFormat", F);
            if (f != null && f.FieldType.IsEnum)
            {
                f.SetValue(opts, EnumBinary(f.FieldType));
                return true;
            }
        }
        return false;
    }

    // オプションオブジェクトの任意設定をsetterメソッド/プロパティ/フィールドの順で試す
    static bool TrySetOption(object opts, string setterName, string propName,
                             string fieldName, object value)
    {
        const BindingFlags F = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        for (var t = opts.GetType(); t != null; t = t.BaseType)
        {
            var m = t.GetMethod(setterName, F);
            if (m != null && m.GetParameters().Length == 1)
            {
                m.Invoke(opts, new[] { value });
                return true;
            }
            var p = t.GetProperty(propName, F);
            if (p != null && p.CanWrite)
            {
                p.SetValue(opts, value, null);
                return true;
            }
            var f = t.GetField(fieldName, F);
            if (f != null)
            {
                f.SetValue(opts, value);
                return true;
            }
        }
        return false;
    }

    static object EnumBinary(Type enumType)
    {
        try { return Enum.Parse(enumType, "Binary"); }
        catch { return Enum.ToObject(enumType, 1); }  // ExportFormat { ASCII=0, Binary=1 }
    }

    static void ExportHumanoid(GameObject go, string outDir)
    {
        var animator = go.GetComponentInChildren<Animator>();
        if (animator == null || animator.avatar == null || !animator.avatar.isHuman)
            throw new Exception("Humanoid設定されたAvatarが見つかりません");
        var sb = new StringBuilder();
        sb.Append("{\n  \"format\": \"divetopalworld-humanoid-1\",\n");
        // D2P平坦化済みの印: step01がメッシュ行列=アーマチュア行列の固定を行う
        sb.Append("  \"d2p_flattened\": true,\n");
        // ルートボーン復元のフォールバック用: Hipsのルート基準位置(Unity座標・m)
        var hipsT = animator.GetBoneTransform(HumanBodyBones.Hips);
        if (hipsT != null)
        {
            var p = go.transform.InverseTransformPoint(hipsT.position);
            sb.AppendFormat(System.Globalization.CultureInfo.InvariantCulture,
                "  \"hips_local\": [{0}, {1}, {2}],\n", p.x, p.y, p.z);
        }
        sb.Append("  \"humanoid\": {\n");
        bool first = true;
        foreach (var hb in animator.avatar.humanDescription.human)
        {
            if (string.IsNullOrEmpty(hb.boneName)) continue;
            if (!first) sb.Append(",\n");
            first = false;
            sb.AppendFormat("    \"{0}\": \"{1}\"", J(hb.humanName), J(hb.boneName));
        }
        sb.Append("\n  }\n}\n");
        File.WriteAllText(Path.Combine(outDir, "humanoid.json"), sb.ToString(),
            new UTF8Encoding(false));
    }

    static void ExportMaterials(GameObject go, string outDir, string fbxName)
    {
        var texFiles = new Dictionary<Texture, string>();
        var sb = new StringBuilder();
        sb.Append("{\n  \"format\": \"divetopalworld-materials-1\",\n");
        sb.AppendFormat("  \"fbx\": \"{0}\",\n  \"meshes\": {{\n", J(fbxName));
        bool firstMesh = true;
        // SkinnedMeshRenderer(体・服等スキン済み)に加え、MeshRenderer(帽子・
        // リボン等、ボーンへTransform直付けの非スキンアクセサリ。PhysBone/
        // Constraintで動かす構成でVRChatアバターにごく一般的)も走査対象に
        // 含める。従来SkinnedMeshRendererのみだったため、非スキンメッシュは
        // material_map.jsonに載らず、step01_import_vrm.pyの
        // extract_materials_from_unity_map()が単色フォールバックにしていた
        // (2026-07-26実測: shapell_Osakiのベレー帽・リボンが灰色化)。
        // 出力名はどちらもRenderer.name(=GameObject名)で揃える。Blender側は
        // orig_names(FBXインポート時の元オブジェクト名)をキーに
        // mesh_map.get(orig)で引くため、SkinnedMeshRendererと同じ命名規則で
        // 揃える必要がある。
        var seenNames = new HashSet<string>();
        var renderers = new List<Renderer>();
        renderers.AddRange(go.GetComponentsInChildren<SkinnedMeshRenderer>(false));
        renderers.AddRange(go.GetComponentsInChildren<MeshRenderer>(false));
        foreach (var r in renderers)
        {
            Mesh sharedMesh;
            var smr = r as SkinnedMeshRenderer;
            if (smr != null)
                sharedMesh = smr.sharedMesh;
            else
            {
                var mf = r.GetComponent<MeshFilter>();
                sharedMesh = mf != null ? mf.sharedMesh : null;
            }
            if (sharedMesh == null || !r.enabled) continue;
            if (!seenNames.Add(r.name))
            {
                Debug.LogWarning("D2P: material_map.jsonでメッシュ名が重複: " + r.name
                                  + "(先勝ちで無視)");
                continue;
            }
            if (!firstMesh) sb.Append(",\n");
            firstMesh = false;
            sb.AppendFormat("    \"{0}\": [\n", J(r.name));
            var mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                var m = mats[i];
                string tex = null;
                float[] col = { 1, 1, 1, 1 };
                bool twoSided = false;
                string matName = m != null ? m.name : "";
                if (m != null)
                {
                    if (m.mainTexture != null)
                        tex = SaveTexture(m.mainTexture, outDir, texFiles);
                    if (m.HasProperty("_Color"))
                    {
                        var c = m.color;
                        col = new[] { c.r, c.g, c.b, c.a };
                    }
                    // lilToon等: _Cull 0=両面
                    if (m.HasProperty("_Cull"))
                        twoSided = m.GetFloat("_Cull") < 0.5f;
                }
                sb.AppendFormat(
                    "      {{\"material_name\": \"{0}\", \"texture\": {1}, " +
                    "\"color\": [{2}], \"double_sided\": {3}}}{4}\n",
                    J(matName),
                    tex == null ? "null" : "\"" + J(tex) + "\"",
                    string.Join(", ", Array.ConvertAll(col,
                        v => v.ToString(System.Globalization.CultureInfo.InvariantCulture))),
                    twoSided ? "true" : "false",
                    i < mats.Length - 1 ? "," : "");
            }
            sb.Append("    ]");
        }
        sb.Append("\n  }\n}\n");
        File.WriteAllText(Path.Combine(outDir, "material_map.json"), sb.ToString(),
            new UTF8Encoding(false));
    }

    static string SaveTexture(Texture tex, string outDir, Dictionary<Texture, string> cache)
    {
        string cached;
        if (cache.TryGetValue(tex, out cached)) return cached;
        // どんな圧縮形式でもRenderTexture経由で読めるPNGにする
        var rt = RenderTexture.GetTemporary(tex.width, tex.height, 0,
            RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        Graphics.Blit(tex, rt);
        var prev = RenderTexture.active;
        RenderTexture.active = rt;
        var read = new Texture2D(tex.width, tex.height, TextureFormat.RGBA32, false);
        read.ReadPixels(new Rect(0, 0, tex.width, tex.height), 0, 0);
        read.Apply();
        RenderTexture.active = prev;
        RenderTexture.ReleaseTemporary(rt);
        string file = string.Format("tex_{0:00}.png", cache.Count);
        File.WriteAllBytes(Path.Combine(outDir, file), read.EncodeToPNG());
        UnityEngine.Object.DestroyImmediate(read);
        cache[tex] = file;
        return file;
    }

    static string J(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
