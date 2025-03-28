// src/controllers/packageController.ts
import { Context } from 'koa';
import { Db, ObjectId, GridFSBucket } from 'mongodb';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { saveFileToGridFS } from '../utils/gridFS';

// 扩展 Koa 的请求类型
interface KoaRequestWithBody extends Request {
  body: any;
  files?: {
    file?: {
      filepath: string;
      [key: string]: any;
    } | Array<any>;
  };
}

export class PackageController {
  private db: Db;
  private gridFSBucket: GridFSBucket;

  constructor(db: Db) {
    this.db = db;
    this.gridFSBucket = new GridFSBucket(db, { bucketName: 'fs' });
  }

  /**
   * 发布包
   * POST /api/packages/publish
   * 需要 x-api-key 验证，通过中间件 authenticate(db)
   * body: { packageName, version, description }
   * file: 上传的文件，由 koa-body 提供
   */
  async publish(ctx: Context) {
    try {
      // userId 由认证中间件设置在 ctx.state.userId 上
      const userId = ctx.state.userId as ObjectId;
      
      // 使用类型断言来处理请求体
      const request = ctx.request as unknown as KoaRequestWithBody;
      const { packageName, version, description } = request.body as {
        packageName: string;
        version: string;
        description: string;
      };

      // 检查文件是否存在 - 使用类型断言处理文件
      const file = request.files?.file;
      if (!file || Array.isArray(file)) {
        ctx.status = 400;
        ctx.body = { error: '文件未上传' };
        return;
      }

      // 读取文件内容
      const fileBuffer = await fs.promises.readFile(file.filepath);
      const fileName = path.basename(file.filepath);

      // 查找包是否存在
      let pkg = await this.db.collection('packages').findOne({ name: packageName });
      if (pkg) {
        // 若包存在，校验当前用户是否拥有此包权限
        if (!pkg.owner.equals(userId)) {
          ctx.status = 403;
          ctx.body = { error: '无权限发布此包' };
          return;
        }
      } else {
        // 插入新包
        const result = await this.db.collection('packages').insertOne({
          name: packageName,
          description,
          owner: userId,
          createdAt: new Date(),
          updatedAt: new Date(),
          downloads: 0
        });
        pkg = { _id: result.insertedId };
      }

      // 检查版本是否已存在
      const existingVersion = await this.db.collection('versions').findOne({
        package: pkg._id,
        version
      });
      if (existingVersion) {
        ctx.status = 400;
        ctx.body = { error: '版本已存在' };
        return;
      }

      // 计算文件的 sha256
      const sha256 = crypto.createHash('sha256').update(fileBuffer).digest('hex');

      // 上传文件到 GridFS
      const fileId = await saveFileToGridFS(this.gridFSBucket, fileBuffer, {
        filename: path.basename(file.filepath),
        metadata: {
          packageName,
          version
        }
      });

      // 插入版本记录
      const versionResult = await this.db.collection('versions').insertOne({
        package: pkg._id,
        version,
        description,
        sha256,
        fileSize: fileBuffer.length,
        filePath: fileId.toHexString(),
        filename: fileName,
        publishedBy: userId,
        publishedAt: new Date(),
        downloads: 0
      });

      ctx.body = { message: '包发布成功', versionId: versionResult.insertedId };
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 删除包（示例实现）
   * DELETE /api/packages/:packageName
   */
  async deletePackage(ctx: Context) {
    try {
      const userId = ctx.state.userId as ObjectId;
      const { packageName } = ctx.params;
      const pkg = await this.db.collection('packages').findOne({ name: packageName });
      if (!pkg) {
        ctx.status = 404;
        ctx.body = { error: '包不存在' };
        return;
      }
      if (pkg.owner !== userId) {
        ctx.status = 403;
        ctx.body = { error: '无权限删除此包' };
        return;
      }
      await this.db.collection('packages').deleteOne({ _id: pkg._id });
      ctx.body = { message: '包删除成功' };
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 下载包（示例实现）
   * GET /api/packages/:packageName/download/:version
   */
  async download(ctx: Context) {
    try {
      const { packageName, version } = ctx.params;
      // 根据包名查找包，进而获取版本信息
      const pkg = await this.db.collection('packages').findOne({ name: packageName });
      if (!pkg) {
        ctx.status = 404;
        ctx.body = { error: '包不存在' };
        return;
      }
      const versionInfo = await this.db.collection('versions').findOne({
        package: pkg._id,
        version: version
      });
      if (!versionInfo) {
        ctx.status = 404;
        ctx.body = { error: '版本不存在' };
        return;
      }
      // 从 GridFS 中获取文件流
      const fileId = new ObjectId(versionInfo.filePath as string);
      const downloadStream = this.gridFSBucket.openDownloadStream(fileId);

      ctx.set('Content-Type', 'application/octet-stream');
      ctx.set('Content-Disposition', `attachment; filename="${versionInfo.filename}"`);

      ctx.body = downloadStream;
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 搜索包
   * GET /api/packages/search?query=xxx
   */
  async searchPackages(ctx: Context) {
    try {
      const { query } = ctx.request.query as { query: string };
      const packages = await this.db.collection('packages').find({
        name: { $regex: query, $options: 'i' }
      }).toArray();
      ctx.body = packages;
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 获取最新版本（示例实现）
   * GET /api/packages/:packageName/ver
   */
  async getLatestVersion(ctx: Context) {
    try {
      const { packageName } = ctx.params;
      const pkg = await this.db.collection('packages').findOne({ name: packageName });
      if (!pkg) {
        ctx.status = 404;
        ctx.body = { error: '包不存在' };
        return;
      }
      // 按发布时间降序排列取最新版本
      const latestVersion = await this.db.collection('versions').find({ package: pkg._id })
        .sort({ publishedAt: -1 })
        .limit(1)
        .toArray();
      if (latestVersion.length === 0) {
        ctx.body = { message: '暂无版本' };
      } else {
        ctx.body = latestVersion[0];
      }
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }
}