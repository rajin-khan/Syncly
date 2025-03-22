package com.example.syncly;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;
import java.util.Map;

public class FileListAdapter extends RecyclerView.Adapter<FileListAdapter.ViewHolder> {

    private final List<Map<String, String>> fileList;
    private final Context context;

    public FileListAdapter(Context context, List<Map<String, String>> fileList) {
        this.context = context;
        this.fileList = fileList;
    }

    public static class ViewHolder extends RecyclerView.ViewHolder {
        TextView fileName;
        TextView fileProvider;

        public ViewHolder(View view) {
            super(view);
            fileName = view.findViewById(R.id.file_name);
            fileProvider = view.findViewById(R.id.file_provider);
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
    }

    @Override
    public int getItemCount() {
        return fileList.size();
    }
}
