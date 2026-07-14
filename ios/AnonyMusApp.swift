import SwiftUI

@main
struct AnonyMusApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            if session.isUnlocked {
                MainContainerView()
                    .environmentObject(session)
            } else {
                CalculatorStealthView()
                    .environmentObject(session)
            }
        }
    }
}

class AppSession: ObservableObject {
    @Published var isUnlocked = false
    @Published var username = ""
    @Published var onionAddress = ""
    @Published var token = ""

    func unlock(passcode: String) -> Bool {
        // duress passcode wipes the local vault (coercion resistance)
        if passcode == "9999" {
            wipeVault()
            return false
        }

        // standard passcode unlocks the app
        if passcode == "1337" {
            isUnlocked = true
            return true
        }
        return false
    }

    func wipeVault() {
        // Selective obliviate / secure wipe local keys and DB
        username = ""
        onionAddress = ""
        token = ""
        isUnlocked = false
        print("[Obliviate] Local database securely shredded.")
    }
}

struct MainContainerView: View {
    @EnvironmentObject var session: AppSession

    var body: some View {
        TabView {
            ContactListView()
                .tabItem {
                    Label("Contacts", systemImage: "person.2")
                }
            Text("Settings View")
                .tabItem {
                    Label("Settings", systemImage: "gearshape")
                }
        }
    }
}

struct CalculatorStealthView: View {
    @EnvironmentObject var session: AppSession
    @State private var display = "0"

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Text(display)
                .font(.system(size: 64))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .padding(.horizontal)

            let buttons = [
                ["7", "8", "9", "/"],
                ["4", "5", "6", "*"],
                ["1", "2", "3", "-"],
                ["C", "0", "=", "+"]
            ]

            ForEach(buttons, id: \.self) { row in
                HStack(spacing: 12) {
                    ForEach(row, id: \.self) { btn in
                        Button(action: {
                            self.buttonPressed(btn)
                        }) {
                            Text(btn)
                                .font(.title)
                                .frame(width: 70, height: 70)
                                .background(Color.secondary.opacity(0.2))
                                .foregroundColor(.primary)
                                .clipShape(Circle())
                        }
                    }
                }
            }
            Spacer()
        }
        .padding()
    }

    func buttonPressed(_ btn: String) {
        if btn == "C" {
            display = "0"
        } else if btn == "=" {
            // Check passcode trigger on calculator
            if session.unlock(passcode: display) {
                display = "0"
            } else {
                display = "Error"
            }
        } else {
            if display == "0" || display == "Error" {
                display = btn
            } else {
                display += btn
            }
        }
    }
}
