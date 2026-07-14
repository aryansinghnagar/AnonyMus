import SwiftUI

struct LoginView: View {
    @EnvironmentObject var session: AppSession
    @State private var username = ""
    @State private var password = ""
    @State private var errorMsg = ""

    var body: some View {
        VStack(spacing: 20) {
            Text("AnonyMus Secure Log In")
                .font(.largeTitle)
                .bold()
                .padding(.bottom, 20)

            TextField("Username", text: $username)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .autocapitalization(.none)
                .disableAutocorrection(true)

            SecureField("Password", text: $password)
                .textFieldStyle(RoundedBorderTextFieldStyle())

            if !errorMsg.isEmpty {
                Text(errorMsg)
                    .foregroundColor(.red)
                    .font(.caption)
            }

            Button(action: handleLogin) {
                Text("Log In")
                    .bold()
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(8)
            }

            Spacer()
        }
        .padding()
    }

    func handleLogin() {
        guard !username.isEmpty && !password.isEmpty else {
            errorMsg = "Fields cannot be empty."
            return
        }

        // Simulates calling the backend routing through onion / local proxy
        session.username = username
        session.onionAddress = "anonymus_onion_address_mock"
        session.token = "session_token_example"
        session.isUnlocked = true
    }
}
