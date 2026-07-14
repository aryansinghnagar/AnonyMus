package com.anonymus.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.anonymus.app.data.ChatMessage
import kotlinx.coroutines.flow.Flow

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages ORDER BY timestamp ASC")
    fun getAllMessagesFlow(): Flow<List<ChatMessage>>

    @Query("SELECT * FROM messages ORDER BY timestamp ASC")
    suspend fun getAllMessages(): List<ChatMessage>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertMessage(message: ChatMessage)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertMessages(messages: List<ChatMessage>)

    @Query("UPDATE messages SET text = :text, isEdited = 1, editHistory = :editHistory WHERE id = :id")
    suspend fun updateMessageText(id: String, text: String, editHistory: List<String>)

    @Query("UPDATE messages SET reactions = :reactions WHERE id = :id")
    suspend fun updateMessageReactions(id: String, reactions: List<String>)

    @Query("UPDATE messages SET fileProgress = :progress WHERE id = :id")
    suspend fun updateFileProgress(id: String, progress: Float)

    @Query("UPDATE messages SET deliveryState = :state WHERE id = :id")
    suspend fun updateDeliveryState(id: String, state: String)

    @Query("DELETE FROM messages WHERE id = :id")
    suspend fun deleteMessage(id: String)

    @Query("DELETE FROM messages")
    suspend fun clearAllMessages()
}
