// 通知ヘルパー: UNUserNotificationCenter で通知の許可を求める・出す・消すだけの CLI。
// ツールごとに別の .app（ClaudeNotify.app 等）としてビルドされ、名前は Info.plist の CFBundleName から取る。
// .app バンドルの中の Contents/MacOS/<Name> を直接 exec して使う
// （バンドル外にコピーしたバイナリでは UNUserNotificationCenter.current() がクラッシュする）。
// LaunchServices への登録（build.sh が lsregister する）が無いと許可も投稿も失敗する。
// 呼び出し側は agent_tooling/notify/macos.py（Python）。終了コードを変えたらそちらも合わせる。
//
// サブコマンド:
//   - authorize: 許可を求める。ユーザーが答えるまで戻らないので、手動で 1 回だけ実行する
//   - post --id <id> --title <t> --subtitle <s> --body <b> [--sound <name>]:
//     同じ id の通知を消してから出し直す（同じ id の add だけではバナーが再表示されないため）
//   - remove --id <id>: その id の表示済み・未配信の通知を消す
//
// 終了コード: 0 成功、2 許可が未決定、3 拒否されている、1 その他のエラー（stderr に理由）。
// stdout には何も書かない（UserPromptSubmit フックのコンテキストに入るのを避けるため）。
import Foundation
import UserNotifications

enum Exit: Int32 {
    case ok = 0
    case failure = 1
    case notDetermined = 2
    case denied = 3
}

let timeout: DispatchTimeInterval = .seconds(5)

// appName は stderr の接頭辞や案内文に使うツール名（ClaudeNotify 等）。
let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String ?? "notify-helper"

func fail(_ message: String, _ code: Exit = .failure) -> Never {
    FileHandle.standardError.write(Data("\(appName): \(message)\n".utf8))
    exit(code.rawValue)
}

// wait は completion handler の呼び出しを待つ。上限に達したら exit 1 で終わる。
func wait(_ what: String, _ body: (@escaping () -> Void) -> Void) {
    let sem = DispatchSemaphore(value: 0)
    body { sem.signal() }
    if sem.wait(timeout: .now() + timeout) == .timedOut {
        fail("\(what) がタイムアウトしました")
    }
}

func parseOptions(_ args: ArraySlice<String>) -> [String: String] {
    var opts: [String: String] = [:]
    var it = args.makeIterator()
    while let key = it.next() {
        guard key.hasPrefix("--"), let value = it.next() else {
            fail("引数が不正です: \(key)")
        }
        opts[String(key.dropFirst(2))] = value
    }
    return opts
}

// requireAuthorized は許可の状態を確認するだけで、requestAuthorization は呼ばない
// （未決定のままフックから求めると、ユーザーが答えるまでプロセスが止まるため）。
func requireAuthorized(_ center: UNUserNotificationCenter) {
    var status = UNAuthorizationStatus.notDetermined
    wait("getNotificationSettings") { done in
        center.getNotificationSettings { settings in
            status = settings.authorizationStatus
            done()
        }
    }
    switch status {
    case .notDetermined:
        fail("通知の許可が未決定です（authorize を実行してください）", .notDetermined)
    case .denied:
        fail("通知が拒否されています", .denied)
    default:
        return
    }
}

// remove は削除 API に完了通知が無いため、getDeliveredNotifications の完了を待って反映させる
// （呼んだ直後に exit すると消えない）。
func remove(_ center: UNUserNotificationCenter, id: String) {
    center.removeDeliveredNotifications(withIdentifiers: [id])
    center.removePendingNotificationRequests(withIdentifiers: [id])
    wait("getDeliveredNotifications") { done in
        center.getDeliveredNotifications { _ in done() }
    }
}

func authorize(_ center: UNUserNotificationCenter) {
    let sem = DispatchSemaphore(value: 0)
    var result: (Bool, Error?) = (false, nil)
    center.requestAuthorization(options: [.alert, .sound]) { granted, error in
        result = (granted, error)
        sem.signal()
    }
    sem.wait()
    if let error = result.1 {
        fail("requestAuthorization 失敗: \(error)")
    }
    if !result.0 {
        fail("通知が拒否されました（システム設定 → 通知 → \(appName) でオンにできます）", .denied)
    }
}

func post(_ center: UNUserNotificationCenter, _ opts: [String: String]) {
    guard let id = opts["id"], !id.isEmpty else { fail("--id がありません") }
    requireAuthorized(center)

    let content = UNMutableNotificationContent()
    content.title = opts["title"] ?? ""
    content.subtitle = opts["subtitle"] ?? ""
    content.body = opts["body"] ?? ""
    if let sound = opts["sound"], !sound.isEmpty {
        content.sound = UNNotificationSound(named: UNNotificationSoundName(sound))
    }

    remove(center, id: id)
    var addError: Error?
    wait("add") { done in
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: nil)) { error in
            addError = error
            done()
        }
    }
    if let addError {
        fail("add 失敗: \(addError)")
    }
}

let args = CommandLine.arguments.dropFirst()
// 引数なし（通知のクリック等で起動された場合）は何もしない
guard let command = args.first else { exit(Exit.ok.rawValue) }
let opts = parseOptions(args.dropFirst())
let center = UNUserNotificationCenter.current()

switch command {
case "authorize":
    authorize(center)
case "post":
    post(center, opts)
case "remove":
    guard let id = opts["id"], !id.isEmpty else { fail("--id がありません") }
    requireAuthorized(center)
    remove(center, id: id)
default:
    fail("不明なサブコマンドです: \(command)")
}
exit(Exit.ok.rawValue)
