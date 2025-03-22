package com.example.syncly;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;

import java.util.List;
import java.util.Map;

public class FileListAdapter extends RecyclerView.Adapter<FileListAdapter.ViewHolder> {

    private final List<Map<String, String>> fileList;
    private final Context context;
    private final OnFileClickListener listener;

    public FileListAdapter(Context context, List<Map<String, String>> fileList, OnFileClickListener listener) {
        this.context = context;
        this.fileList = fileList;
        this.listener = listener;
    }

    public static class ViewHolder extends RecyclerView.ViewHolder {
        TextView fileName, fileProvider;
        ImageView fileThumbnail;

        public ViewHolder(View view) {
            super(view);
            fileName = view.findViewById(R.id.file_name);
            fileProvider = view.findViewById(R.id.file_provider);
            fileThumbnail = view.findViewById(R.id.file_thumbnail);
        }
    }

    @NonNull
    @Override
    public FileListAdapter.ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(context).inflate(R.layout.item_file, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull FileListAdapter.ViewHolder holder, int position) {
        Map<String, String> file = fileList.get(position);
        holder.fileName.setText(file.get("name"));
        holder.fileProvider.setText(file.get("provider"));

        // For now, use a placeholder thumbnail
        String name = file.get("name");
        assert name != null;
        if (name.endsWith(".pdf")) {
            Glide.with(context).load(R.drawable.ic_pdf_foreground).into(holder.fileThumbnail);
        } else if (name.endsWith(".jpg") || name.endsWith(".png")) {
            Glide.with(context).load(R.drawable.ic_jpg_foreground).into(holder.fileThumbnail);
        } else {
            Glide.with(context).load(R.drawable.ic_file_placeholder_foreground).into(holder.fileThumbnail);
        }
        holder.itemView.setOnClickListener(v -> {
            String url = file.get("url");
            String nameToView = file.get("name");
            if (url != null && !url.isEmpty()) {
                listener.onFileClick(url, nameToView);
            }
        });
    }

    @Override
    public int getItemCount() {
        return fileList.size();
    }

    public interface OnFileClickListener {
        void onFileClick(String fileUrl, String fileName);
    }
}
