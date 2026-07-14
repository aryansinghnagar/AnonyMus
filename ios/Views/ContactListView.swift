import SwiftUI

struct iOSContact: Identifiable {
    let id = UUID()
    let nickname: String
    let onionAddress: String
    let verified: Bool
    let safetyNumber: String
}

struct ContactListView: View {
    @State private var contacts: [iOSContact] = [
        iOSContact(nickname: "Bob", onionAddress: "bobonionaddress12345.onion", verified: true, safetyNumber: "12345 67890 11121 31415 16171 81920"),
        iOSContact(nickname: "Alice", onionAddress: "aliceonionaddress67890.onion", verified: false, safetyNumber: "Pending Verification")
    ]
    @State private var showingAddContact = false
    @State private var newNickname = ""
    @State private var newOnion = ""

    var body: some View {
        NavigationView {
            List(contacts) { contact in
                NavigationLink(destination: ChatView(contact: contact)) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(contact.nickname)
                                .font(.headline)
                            if contact.verified {
                                Image(systemName: "checkmark.seal.fill")
                                    .foregroundColor(.blue)
                            }
                        }
                        Text(contact.onionAddress)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .navigationTitle("Contacts")
            .toolbar {
                Button(action: { showingAddContact = true }) {
                    Image(systemName: "plus")
                }
            }
            .sheet(isPresented: $showingAddContact) {
                VStack(spacing: 20) {
                    Text("Add Secure Contact")
                        .font(.headline)
                    TextField("Nickname", text: $newNickname)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    TextField("Onion Address", text: $newOnion)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    Button("Save") {
                        if !newNickname.isEmpty && !newOnion.isEmpty {
                            contacts.append(iOSContact(nickname: newNickname, onionAddress: newOnion, verified: false, safetyNumber: "Pending"))
                            newNickname = ""
                            newOnion = ""
                            showingAddContact = false
                        }
                    }
                    .padding()
                }
                .padding()
            }
        }
    }
}
